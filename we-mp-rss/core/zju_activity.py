from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup
from sqlalchemy import create_engine

from core.activity_sources import (
    SourceChannelRegistry,
    WechatActivityAdapter,
    WebsiteActivityAdapter,
    build_wechat_sources,
    build_website_sources,
)
from core.activity_sources.common import (
    CORE_DISPLAY_NAMES,
    DEFAULT_HEADERS,
    DETAIL_CONTENT_SELECTORS,
    DETAIL_TITLE_SELECTORS,
    HIGH_SIGNAL_SOURCE_IDS,
    WECHAT_CORE_SOURCE_MAP,
    clean_text,
    extract_labeled_text,
    extract_campus,
    is_evening_time,
    normalize_title_key,
    parse_iso_date,
    to_iso_date,
)
from core.activity_schema import validate_activity_record
from core.app_logging import log_event
from core.print import print_warning


class ZJUActivityService:
    def __init__(self, config_path: str | None = None, cache_ttl: int = 600):
        project_root = Path(__file__).resolve().parents[2]
        self.project_root = project_root
        self.config_path = Path(config_path) if config_path else project_root / "config.json"
        self.cache_ttl = cache_ttl
        self._config_cache = None
        self._config_mtime = None
        self._source_cache: dict[str, dict] = {}
        self._detail_cache: dict[str, dict] = {}
        self._wechat_db_engine = None
        self._wechat_db_url = None
        self._source_status: dict[str, dict] = {}
        self._last_generated_at: str | None = None
        self._last_freshness: str | None = None
        self._lock = threading.Lock()
        self._source_registry = SourceChannelRegistry(
            core_display_names=CORE_DISPLAY_NAMES,
            wechat_core_source_map=WECHAT_CORE_SOURCE_MAP,
        )
        self._source_registry.register(
            "website",
            builder=build_website_sources,
            adapter=WebsiteActivityAdapter(),
            service_method_name="_fetch_source_items",
            source_builder_method_name="_build_website_sources",
        )
        self._source_registry.register(
            "wechat",
            builder=build_wechat_sources,
            adapter=WechatActivityAdapter(),
            service_method_name="_fetch_wechat_items",
            source_builder_method_name="_build_wechat_sources",
        )

    def _load_config(self) -> dict:
        mtime = self.config_path.stat().st_mtime
        if self._config_cache is not None and self._config_mtime == mtime:
            return self._config_cache

        with self.config_path.open("r", encoding="utf-8") as fp:
            self._config_cache = json.load(fp)
        self._config_mtime = mtime
        return self._config_cache

    def _expand_env_template(self, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value

        pattern = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")

        def replace_match(match):
            env_name = match.group(1)
            default_value = match.group(2)
            return os.getenv(env_name, default_value or "")

        return pattern.sub(replace_match, value)

    def _load_wechat_db_url(self) -> str | None:
        config_path = self.project_root / "we-mp-rss" / "config.yaml"
        if not config_path.exists():
            return None

        with config_path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}

        db_url = self._expand_env_template(data.get("db"))
        if not db_url:
            return None

        if db_url.startswith("sqlite:///"):
            raw_path = db_url[10:]
            if raw_path and not raw_path.startswith("/"):
                resolved_path = (config_path.parent / raw_path).resolve()
                return f"sqlite:///{resolved_path}"

        return db_url

    def _get_wechat_db_engine(self):
        db_url = self._load_wechat_db_url()
        if not db_url:
            return None

        if self._wechat_db_engine is not None and self._wechat_db_url == db_url:
            return self._wechat_db_engine

        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite:///") else {}
        self._wechat_db_engine = create_engine(db_url, connect_args=connect_args)
        self._wechat_db_url = db_url
        return self._wechat_db_engine

    def _build_website_sources(self) -> list[dict]:
        return self._source_registry.build_channel_sources("website", self._load_config())

    def _build_wechat_sources(self) -> list[dict]:
        return self._source_registry.build_channel_sources("wechat", self._load_config())

    def _build_sources(self) -> list[dict]:
        return self._source_registry.build_merged_sources(self._load_config())

    def _build_sources_for_channel(self, channel: str) -> list[dict]:
        return self._source_registry.build_channel_sources(channel, self._load_config())

    def _resolve_source(self, source_id: str, source_channel: str | None = None) -> dict:
        channels = [source_channel] if source_channel else self._source_registry.iter_channels()
        matches = []

        for channel in channels:
            if channel not in self._source_registry.iter_channels():
                raise ValueError(f"unsupported_source_channel:{channel}")
            for source in self._build_sources_for_channel(channel):
                if source["id"] == source_id or source.get("cache_key") == source_id:
                    matches.append(source)

        if not matches:
            raise LookupError(f"source_not_found:{source_id}")
        if len(matches) > 1 and not source_channel:
            raise ValueError(f"source_channel_required:{source_id}")
        return matches[0]

    def _clear_source_cache(self, source: dict) -> None:
        cache_keys = {source["id"]}
        cache_key = source.get("cache_key")
        if cache_key:
            cache_keys.add(cache_key)

        with self._lock:
            for key in cache_keys:
                self._source_cache.pop(key, None)

    def _source_status_key(self, source: dict) -> str:
        return f"{source.get('source_channel', 'website')}:{source['id']}"

    def _utc_now_iso(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def _update_source_status(
        self,
        source: dict,
        *,
        ok: bool,
        item_count: int = 0,
        error: str | None = None,
        cached: bool = False,
    ) -> None:
        status_key = self._source_status_key(source)
        now = self._utc_now_iso()

        with self._lock:
            previous = self._source_status.get(status_key, {})
            next_status = {
                "id": source["id"],
                "name": source["name"],
                "source_type": source.get("source_type"),
                "source_channel": source.get("source_channel"),
                "last_attempt_at": now,
                "last_success_at": previous.get("last_success_at"),
                "last_error_at": previous.get("last_error_at"),
                "last_error": previous.get("last_error"),
                "last_item_count": item_count if ok else previous.get("last_item_count", 0),
                "cached": cached,
                "consecutive_failures": previous.get("consecutive_failures", 0),
            }

            if ok:
                next_status["status"] = "ok"
                next_status["last_success_at"] = now
                next_status["last_error"] = None
                next_status["last_error_at"] = None
                next_status["consecutive_failures"] = 0
            else:
                next_status["status"] = "error"
                next_status["last_error"] = error
                next_status["last_error_at"] = now
                next_status["consecutive_failures"] = previous.get("consecutive_failures", 0) + 1

            self._source_status[status_key] = next_status

    def get_source_status_summary(self) -> dict:
        sources = self._build_sources()
        source_order = {
            self._source_status_key(source): index
            for index, source in enumerate(sources)
        }

        with self._lock:
            items = list(self._source_status.values())

        items.sort(key=lambda item: source_order.get(f"{item.get('source_channel', 'website')}:{item['id']}", 9999))
        ok_count = sum(1 for item in items if item.get("status") == "ok")
        error_count = sum(1 for item in items if item.get("status") == "error")
        last_success_sync_at = max(
            (item.get("last_success_at") for item in items if item.get("last_success_at")),
            default=None,
        )

        return {
            "generated_at": self._last_generated_at,
            "freshness": self._last_freshness,
            "last_success_sync_at": last_success_sync_at,
            "total_sources": len(sources),
            "attempted_sources": len(items),
            "ok_sources": ok_count,
            "error_sources": error_count,
            "items": items,
        }

    def _compute_freshness(self, *, total: int, summary: dict) -> str:
        if summary["attempted_sources"] == 0:
            return "cold"
        if summary["ok_sources"] == 0:
            return "degraded"
        if summary["error_sources"] > 0:
            return "partial"
        if total > 0:
            return "fresh"
        return "empty"

    def get_runtime_health(self) -> dict:
        summary = self.get_source_status_summary()
        status = "unknown"
        if summary["attempted_sources"] == 0:
            status = "cold"
        elif summary["ok_sources"] == 0:
            status = "degraded"
        elif summary["error_sources"] > 0:
            status = "partial"
        else:
            status = "healthy"

        return {
            "status": status,
            "generated_at": summary["generated_at"],
            "last_success_sync_at": summary["last_success_sync_at"],
            "sources": {
                "total": summary["total_sources"],
                "attempted": summary["attempted_sources"],
                "ok": summary["ok_sources"],
                "error": summary["error_sources"],
            },
        }

    def _validate_activities(self, items: list[dict]) -> tuple[list[dict], dict]:
        valid_items = []
        dropped_by_source: dict[str, int] = {}
        invalid_examples = []

        for item in items:
            validated, error = validate_activity_record(item)
            if validated is not None:
                valid_items.append(validated)
                continue

            source_id = item.get("college_id") or "unknown"
            dropped_by_source[source_id] = dropped_by_source.get(source_id, 0) + 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        "id": item.get("id"),
                        "college_id": source_id,
                        "title": item.get("title"),
                        "error": error,
                    }
                )

        return valid_items, {
            "valid_count": len(valid_items),
            "dropped_count": len(items) - len(valid_items),
            "dropped_by_source": dropped_by_source,
            "invalid_examples": invalid_examples,
        }

    def _build_source_metrics(self, items: list[dict], validation_summary: dict) -> list[dict]:
        source_index = {
            source["id"]: {
                "id": source["id"],
                "name": source["name"],
                "source_type": source["source_type"],
                "source_channels": source.get("source_channels", [source.get("source_channel")] if source.get("source_channel") else []),
                "activity_count": 0,
                "upcoming_count": 0,
                "complete_info_count": 0,
                "dropped_invalid_count": validation_summary["dropped_by_source"].get(source["id"], 0),
            }
            for source in self._build_sources()
        }

        for item in items:
            metrics = source_index.get(item["college_id"])
            if metrics is None:
                metrics = {
                    "id": item["college_id"],
                    "name": item["college_name"],
                    "source_type": item.get("source_type"),
                    "source_channels": [item.get("source_channel")] if item.get("source_channel") else [],
                    "activity_count": 0,
                    "upcoming_count": 0,
                    "complete_info_count": 0,
                    "dropped_invalid_count": validation_summary["dropped_by_source"].get(item["college_id"], 0),
                }
                source_index[item["college_id"]] = metrics

            metrics["activity_count"] += 1
            if item.get("is_upcoming"):
                metrics["upcoming_count"] += 1
            if item.get("has_complete_info"):
                metrics["complete_info_count"] += 1

        output = []
        for metrics in source_index.values():
            activity_count = metrics["activity_count"]
            metrics["info_completeness_ratio"] = round(
                metrics["complete_info_count"] / activity_count, 3
            ) if activity_count else 0.0
            output.append(metrics)

        return output

    def get_colleges(self) -> list[dict]:
        return [
            {
                "id": source["id"],
                "name": source["name"],
                "category": source["category"],
                "source_type": source["source_type"],
                "url": source["url"],
                "source_channels": source.get("source_channels", [source.get("source_channel")] if source.get("source_channel") else []),
            }
            for source in self._build_sources()
        ]

    def _pick_nodes(self, soup: BeautifulSoup, selectors: list[str]) -> list:
        for selector in selectors:
            try:
                nodes = soup.select(selector)
            except Exception:
                continue
            nodes = [node for node in nodes if node.select_one("a")]
            if nodes:
                return nodes
        return []

    def _pick_node(self, node, selectors: list[str]):
        for selector in selectors:
            try:
                target = node.select_one(selector)
            except Exception:
                continue
            if target:
                return target
        return None

    def _pick_text(self, node, selectors: list[str]) -> str:
        for selector in selectors:
            target = node.select_one(selector)
            if not target:
                continue
            text = clean_text(target.get_text(" ", strip=True))
            if text:
                return text
        return ""

    def _pick_anchor(self, node, selectors: list[str]):
        for selector in selectors:
            anchor = node.select_one(selector)
            if anchor and anchor.name == "a":
                return anchor
        return node.select_one("a")

    def _extract_title_and_anchor(self, node, selectors: list[str]):
        title_node = self._pick_node(node, selectors)
        anchor = None
        title = ""

        if title_node:
            if title_node.name == "a":
                anchor = title_node
                title = clean_text(title_node.get("title") or title_node.get_text(" ", strip=True))
            else:
                title = clean_text(title_node.get_text(" ", strip=True))
                for parent in title_node.parents:
                    if getattr(parent, "name", None) == "a":
                        anchor = parent
                        break

        if not anchor:
            anchor = node.select_one("a")
        if not title and anchor:
            title = clean_text(anchor.get("title") or anchor.get_text(" ", strip=True))

        return title, anchor

    def _fetch_html(self, url: str) -> str:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _is_cache_entry_fresh(self, timestamp: float) -> bool:
        return time.time() - timestamp < self.cache_ttl

    def _store_cached_source_items(self, cache_key: str, items: list[dict]) -> None:
        with self._lock:
            self._source_cache[cache_key] = {
                "timestamp": time.time(),
                "items": items,
            }

    def _get_days_until(self, activity_date: str | None) -> int | None:
        target = parse_iso_date(activity_date)
        if not target:
            return None
        return (target - date.today()).days

    def _compute_student_score(self, activity: dict) -> int:
        score = 0
        days_until = activity.get("days_until")

        if days_until is None:
            score -= 1
        elif days_until < 0:
            score -= 8
        elif days_until == 0:
            score += 8
        elif days_until == 1:
            score += 7
        elif days_until <= 3:
            score += 5
        elif days_until <= 7:
            score += 3
        else:
            score += 1

        if activity.get("source_type") == "core":
            score += 4

        if activity.get("college_id") in HIGH_SIGNAL_SOURCE_IDS:
            score += 3

        if activity.get("has_complete_info"):
            score += 3

        if activity.get("campus"):
            score += 1

        if activity.get("speaker"):
            score += 1

        if is_evening_time(activity.get("activity_time")):
            score += 1

        preview_text = f"{activity.get('title', '')} {activity.get('description', '')}".lower()
        if re.search(r"(求真一小时|讲坛|讲堂|论坛|分享会|career|guide|训练营|人工智能|大模型)", preview_text, flags=re.I):
            score += 1

        if re.search(r"(研究生)", preview_text, flags=re.I):
            score -= 1

        return score

    def _build_info_completeness(self, activity: dict) -> dict:
        tracked_fields = {
            "日期": bool(activity.get("activity_date")),
            "时间": bool(activity.get("activity_time")),
            "地点": bool(activity.get("location")),
            "主讲人": bool(activity.get("speaker")),
            "简介": bool(activity.get("description")),
            "原文链接": bool(activity.get("source_url")),
        }
        present_count = sum(1 for present in tracked_fields.values() if present)
        total_count = len(tracked_fields)
        score = round(present_count / total_count, 3) if total_count else 0.0
        missing_fields = [label for label, present in tracked_fields.items() if not present]

        if score >= 0.84 and activity.get("activity_time") and activity.get("location"):
            level = "complete"
        elif score >= 0.5:
            level = "partial"
        else:
            level = "limited"

        return {
            "info_completeness_score": score,
            "info_completeness_level": level,
            "info_missing_fields": missing_fields,
        }

    def _build_source_confidence(self, activity: dict) -> dict:
        score = 0.4
        reasons = []

        if activity.get("source_type") == "core":
            score += 0.2
            reasons.append("校级官方来源")
        elif activity.get("source_type") == "college":
            score += 0.12
            reasons.append("学院官方来源")

        if activity.get("source_channel") == "website":
            score += 0.15
            reasons.append("官网结构化抓取")
        elif activity.get("source_channel") == "wechat":
            score += 0.05
            reasons.append("公众号文章抽取")

        if activity.get("has_complete_info"):
            score += 0.1
            reasons.append("时间地点明确")
        if activity.get("speaker"):
            score += 0.05
            reasons.append("主讲人明确")
        if len(activity.get("description") or "") >= 40:
            score += 0.05
            reasons.append("活动说明较完整")
        if activity.get("registration_required"):
            score += 0.03
            reasons.append("包含报名信息")

        score = round(min(score, 0.98), 3)
        if score >= 0.8:
            level = "high"
        elif score >= 0.6:
            level = "medium"
        else:
            level = "low"

        return {
            "source_confidence_score": score,
            "source_confidence_level": level,
            "source_confidence_reasons": reasons,
        }

    def _build_preview_reason(self, activity: dict) -> str:
        if activity.get("source_type") == "core":
            return "校级入口"

        if activity.get("campus"):
            return f"{activity['campus']}校区"

        if is_evening_time(activity.get("activity_time")):
            return "晚间场"

        if activity.get("has_complete_info"):
            return "时间地点明确"

        if activity.get("speaker"):
            return "主讲人明确"

        if activity.get("is_upcoming"):
            return "近期活动"

        return "历史活动"

    def _decorate_activity(self, activity: dict) -> dict:
        decorated = dict(activity)
        campus = activity.get("campus") or extract_campus(activity.get("location"))
        days_until = self._get_days_until(activity.get("activity_date"))
        has_complete_info = bool(activity.get("activity_time") and activity.get("location"))

        decorated["campus"] = campus
        decorated["days_until"] = days_until
        decorated["is_upcoming"] = days_until is not None and days_until >= 0
        decorated["has_complete_info"] = has_complete_info
        decorated["preview_reason"] = self._build_preview_reason(
            {
                **decorated,
                "campus": campus,
                "days_until": days_until,
                "has_complete_info": has_complete_info,
                "is_upcoming": days_until is not None and days_until >= 0,
            }
        )
        decorated["student_score"] = self._compute_student_score(
            {
                **decorated,
                "campus": campus,
                "days_until": days_until,
                "has_complete_info": has_complete_info,
            }
        )
        decorated.update(self._build_info_completeness(decorated))
        decorated.update(self._build_source_confidence(decorated))
        return decorated

    def _fetch_wechat_items(self, source: dict) -> list[dict]:
        return self._source_registry.get_adapter("wechat").fetch(self, source)

    def _dedupe_activities(self, items: list[dict]) -> list[dict]:
        best_by_key = {}
        ordered_keys = []

        def quality(item: dict):
            return (
                1 if item.get("activity_time") else 0,
                1 if item.get("location") else 0,
                1 if item.get("speaker") else 0,
                1 if item.get("source_channel") == "wechat" else 0,
                len(item.get("description") or ""),
            )

        for item in items:
            title_key = normalize_title_key(item.get("title"))
            activity_date = item.get("activity_date")
            if not title_key or not activity_date:
                key = item["id"]
            else:
                key = (item.get("college_id"), activity_date, title_key)

            if key not in best_by_key:
                best_by_key[key] = item
                ordered_keys.append(key)
                continue

            if quality(item) > quality(best_by_key[key]):
                best_by_key[key] = item

        return [best_by_key[key] for key in ordered_keys]

    def _extract_detail_text_value(self, text: str, patterns: list[str]) -> str | None:
        return extract_labeled_text(
            text,
            inline_patterns=patterns,
            labels=[],
        )

    def _enrich_activity_detail(self, activity: dict) -> dict:
        source_url = activity.get("source_url")
        if not source_url:
            return activity

        with self._lock:
            cached = self._detail_cache.get(source_url)
            if cached and time.time() - cached["timestamp"] < self.cache_ttl:
                merged = dict(activity)
                merged.update(cached["data"])
                return merged

        try:
            html = self._fetch_html(source_url)
        except Exception as exc:
            print_warning(f"抓取活动详情失败: {source_url} -> {exc}")
            log_event("warning", "activity detail fetch failed", source_url=source_url, error=exc)
            return activity

        soup = BeautifulSoup(html, "html.parser")
        title_node = self._pick_node(soup, DETAIL_TITLE_SELECTORS)
        content_node = self._pick_node(soup, DETAIL_CONTENT_SELECTORS)

        detail_title = None
        if title_node:
            detail_title = clean_text(title_node.get_text(" ", strip=True))

        body_text = ""
        if content_node:
            body_text = content_node.get_text("\n", strip=True)
        body_text = re.sub(r"\n{2,}", "\n", body_text).strip()

        meta_description = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", attrs={"property": "og:description"})
        )
        description = None
        if meta_description and meta_description.get("content"):
            description = clean_text(meta_description.get("content"))
        if not description and body_text:
            description = clean_text(body_text[:280])

        time_label_pattern = (
            r"(?:(?:活动时间|讲座时间)\s*(?:[:：]\s*|(?=[0-9０-９一二三四五六日天上下早中晚今明本周星期（(]))|"
            r"时\s*间\s*(?:[:：]\s*|(?=[0-9０-９一二三四五六日天上下早中晚今明本周星期（(]))"
            r")"
        )
        speaker = extract_labeled_text(
            body_text,
            inline_patterns=[r"(?:主讲人|报告人|演讲人)\s*[:：]?\s*([^\n]+)"],
            labels=["主讲人", "报告人", "演讲人"],
            stop_labels=["时间", "地点", "活动时间", "活动地点", "主讲人简介"],
        )
        activity_time = extract_labeled_text(
            body_text,
            inline_patterns=[rf"{time_label_pattern}([^\n]+)"],
            labels=["活动时间", "讲座时间", "时间"],
            stop_labels=["地点", "活动地点", "讲座地点", "主讲人", "报告人", "演讲人", "主讲人简介"],
        )
        location = extract_labeled_text(
            body_text,
            inline_patterns=[r"(?:活动地点|讲座地点|地\s*点)\s*(?:[:：]\s*)?([^\n]+)"],
            labels=["活动地点", "讲座地点", "地点"],
            stop_labels=["时间", "活动时间", "讲座时间", "主讲人", "报告人", "演讲人", "主讲人简介"],
        )

        cover_image = None
        meta_image = (
            soup.find("meta", attrs={"property": "og:image"})
            or soup.find("meta", attrs={"name": "og:image"})
        )
        if meta_image and meta_image.get("content"):
            cover_image = urljoin(source_url, meta_image["content"])
        elif content_node:
            first_img = content_node.find("img")
            if first_img and first_img.get("src"):
                cover_image = urljoin(source_url, first_img["src"])

        registration_link = None
        if content_node:
            for link in content_node.find_all("a", href=True):
                link_text = clean_text(link.get_text(" ", strip=True))
                if any(keyword in link_text for keyword in ["报名", "预约", "注册链接"]):
                    registration_link = urljoin(source_url, link["href"])
                    break

        enriched = {}
        if detail_title:
            enriched["title"] = detail_title
        if description:
            enriched["description"] = description
        if speaker and not activity.get("speaker"):
            enriched["speaker"] = speaker
        if activity_time and not activity.get("activity_time"):
            enriched["activity_time"] = activity_time
            enriched["activity_date"] = to_iso_date(activity_time) or activity.get("activity_date")
        if location and not activity.get("location"):
            enriched["location"] = location
        if cover_image:
            enriched["cover_image"] = cover_image
        if registration_link:
            enriched["registration_required"] = True
            enriched["registration_link"] = registration_link

        with self._lock:
            self._detail_cache[source_url] = {
                "timestamp": time.time(),
                "data": enriched,
            }

        merged = dict(activity)
        merged.update(enriched)
        return merged

    def _fetch_source_items(self, source: dict) -> list[dict]:
        return self._source_registry.get_adapter("website").fetch(self, source)

    def _fetch_items_for_source(self, source: dict) -> list[dict]:
        fetcher = self._source_registry.get_service_fetcher(self, source["source_channel"])
        return fetcher(source)

    def list_activities(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        college_id: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 100,
        refresh: bool = False,
        student_view: bool = False,
        sort_by: str = "date",
        upcoming_only: bool = False,
    ) -> dict:
        if refresh:
            from core.activity_scraper import scrape_and_persist
            import threading
            t = threading.Thread(target=scrape_and_persist, daemon=True)
            t.start()
            t.join(timeout=60)

        generated_at = self._utc_now_iso()
        self._last_generated_at = generated_at

        # 从数据库读取活动
        collected = self._load_activities_from_db()

        # 如果数据库为空，回退到实时抓取（首次启动、采集尚未完成时）
        if not collected:
            collected = self._fetch_all_activities_live()

        collected, validation_summary = self._validate_activities(collected)

        if college_id and college_id != "all":
            collected = [item for item in collected if item["college_id"] == college_id]

        if keyword:
            needle = keyword.lower()
            collected = [
                item
                for item in collected
                if needle in item["title"].lower()
                or needle in (item.get("description") or "").lower()
                or needle in item["college_name"].lower()
            ]

        if start_date:
            collected = [item for item in collected if item["activity_date"] >= start_date]

        if end_date:
            collected = [item for item in collected if item["activity_date"] <= end_date]

        collected = [self._decorate_activity(item) for item in collected]
        source_metrics = self._build_source_metrics(collected, validation_summary)

        if upcoming_only:
            collected = [item for item in collected if item.get("is_upcoming")]

        if student_view and sort_by == "date":
            sort_by = "relevance"

        if sort_by == "relevance":
            collected.sort(
                key=lambda item: (
                    -item.get("student_score", 0),
                    item.get("days_until") if item.get("days_until") is not None else 9999,
                    item["title"],
                )
            )
        else:
            collected.sort(key=lambda item: (item["activity_date"], item["title"]))

        total = len(collected)
        offset = max(page - 1, 0) * limit
        paged = collected[offset:offset + limit]
        source_status = self.get_source_status_summary()
        freshness = self._compute_freshness(total=total, summary=source_status)
        self._last_freshness = freshness
        source_status["freshness"] = freshness

        return {
            "list": paged,
            "total": total,
            "page": page,
            "limit": limit,
            "sources": len(self._build_sources()),
            "sort_by": sort_by,
            "student_view": student_view,
            "generated_at": generated_at,
            "last_success_sync_at": source_status.get("last_success_sync_at"),
            "freshness": freshness,
            "validation": validation_summary,
            "source_status": source_status,
            "source_metrics": source_metrics,
        }

    def _load_activities_from_db(self) -> list[dict]:
        """从 activities 表读取所有活动记录。"""
        try:
            from core.db import DB
            from core.models.activity import Activity as ActivityModel
            session = DB.get_session()
            rows = session.query(ActivityModel).filter(
                (ActivityModel.record_bucket.is_(None)) | (ActivityModel.record_bucket != "non_activity")
            ).all()
            return [row.to_dict() for row in rows]
        except Exception as exc:
            print_warning(f"从数据库读取活动失败，将回退到实时抓取: {exc}")
            return []

    def _fetch_all_activities_live(self) -> list[dict]:
        """回退路径：实时抓取所有来源（数据库为空时使用）。"""
        collected = []
        for channel in self._source_registry.iter_channels():
            build_sources = self._source_registry.get_service_source_builder(self, channel)
            for source in build_sources():
                try:
                    collected.extend(self._fetch_items_for_source(source))
                except Exception as exc:
                    self._update_source_status(source, ok=False, error=str(exc))
                    if source["source_channel"] == "wechat":
                        print_warning(f"读取公众号活动失败: {source['id']} {source.get('mp_name')} -> {exc}")
                        log_event("warning", "wechat activity source failed", source_id=source["id"], mp_name=source.get("mp_name"), error=exc)
                    else:
                        print_warning(f"抓取活动源失败: {source['id']} {source['url']} -> {exc}")
                        log_event("warning", "website activity source failed", source_id=source["id"], source_url=source["url"], error=exc)
        return self._dedupe_activities(collected)

    def get_activity(self, activity_id: str) -> dict | None:
        # 优先从数据库查单条
        try:
            from core.db import DB
            from core.models.activity import Activity as ActivityModel
            session = DB.get_session()
            row = session.query(ActivityModel).filter(
                ActivityModel.id == activity_id,
                (ActivityModel.record_bucket.is_(None)) | (ActivityModel.record_bucket != "non_activity"),
            ).first()
            if row:
                return self._decorate_activity(self._enrich_activity_detail(row.to_dict()))
        except Exception:
            pass

        # 回退：从列表中查找
        result = self.list_activities(limit=1000)
        for item in result["list"]:
            if item["id"] == activity_id:
                return self._decorate_activity(self._enrich_activity_detail(item))

        return None

    def refresh_source(self, *, source_id: str, source_channel: str | None = None) -> dict:
        source = self._resolve_source(source_id, source_channel)
        self._clear_source_cache(source)

        items = self._fetch_items_for_source(source)
        items = self._dedupe_activities(items)
        valid_items, validation_summary = self._validate_activities(items)
        decorated_items = [self._decorate_activity(item) for item in valid_items]
        source_metrics = self._build_source_metrics(decorated_items, validation_summary)
        source_metric = next((item for item in source_metrics if item["id"] == source["id"]), None)
        source_status = self.get_source_status_summary()

        return {
            "source": {
                "id": source["id"],
                "name": source["name"],
                "source_channel": source["source_channel"],
                "source_type": source.get("source_type"),
                "mp_name": source.get("mp_name"),
            },
            "refresh_mode": "direct_fetch" if source["source_channel"] == "website" else "cache_reload",
            "item_count": len(items),
            "valid_item_count": len(valid_items),
            "dropped_count": validation_summary["dropped_count"],
            "source_metric": source_metric,
            "source_status": next(
                (
                    item
                    for item in source_status["items"]
                    if item["id"] == source["id"] and item.get("source_channel") == source["source_channel"]
                ),
                None,
            ),
            "upstream_sync_required": source["source_channel"] == "wechat",
            "note": (
                "官网来源已直接重新抓取。"
                if source["source_channel"] == "website"
                else "公众号来源已重新加载当前聚合库缓存；如需拉取上游最新文章，请继续使用 /mps/{mp_id}/sync。"
            ),
        }
