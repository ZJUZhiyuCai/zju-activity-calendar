from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.activity_llm import is_activity_llm_enabled, parse_activity_with_llm
from core.print import print_info

from .common import (
    DETAIL_CONTENT_SELECTORS,
    DETAIL_TITLE_SELECTORS,
    FALLBACK_DATE_SELECTORS,
    FALLBACK_ITEM_SELECTORS,
    FALLBACK_TITLE_SELECTORS,
    SKIP_TITLES,
    build_activity_id,
    clean_text,
    dedupe_exact_items,
    merge_selectors,
    strip_prefix,
    to_iso_date,
)


class WebsiteActivityAdapter:
    channel = "website"

    def _fetch_detail_text(self, service, detail_url: str) -> tuple[str | None, str]:
        try:
            detail_html = service._fetch_html(detail_url)
        except Exception:
            return None, ""

        soup = BeautifulSoup(detail_html, "html.parser")
        title_node = service._pick_node(soup, DETAIL_TITLE_SELECTORS)
        content_node = service._pick_node(soup, DETAIL_CONTENT_SELECTORS)

        detail_title = clean_text(title_node.get_text(" ", strip=True)) if title_node else None
        if content_node:
            body_text = content_node.get_text("\n", strip=True)
        elif soup.body:
            body_text = soup.body.get_text("\n", strip=True)
        else:
            body_text = soup.get_text("\n", strip=True)

        normalized_lines = []
        for line in body_text.replace("\r", "\n").splitlines():
            cleaned_line = clean_text(line)
            if cleaned_line:
                normalized_lines.append(cleaned_line)
        return detail_title, "\n".join(normalized_lines).strip()

    def _apply_llm_result(
        self,
        *,
        title: str,
        description: str | None,
        detail_text: str,
        activity: dict,
    ) -> dict | None:
        publish_year = None
        if activity.get("activity_date"):
            try:
                publish_year = datetime.strptime(activity["activity_date"], "%Y-%m-%d").year
            except ValueError:
                publish_year = None

        print_info(f"LLM 解析网页活动: {title[:40]}")
        outcome = parse_activity_with_llm(
            title=title,
            description=description or "",
            body_text=detail_text,
            publish_year=publish_year,
        )

        merged = dict(activity)
        if outcome.result:
            parsed = outcome.result
            print_info(
                "LLM 网页解析完成: "
                f"is_activity={parsed.is_activity} "
                f"date={parsed.activity_date} "
                f"confidence={parsed.confidence}"
            )
            if not parsed.is_activity:
                return None

            if parsed.activity_date:
                merged["activity_date"] = parsed.activity_date
            if parsed.activity_time:
                merged["activity_time"] = parsed.activity_time
            if parsed.location:
                merged["location"] = parsed.location
            if parsed.speaker:
                merged["speaker"] = parsed.speaker
            if parsed.speaker_title:
                merged["speaker_title"] = parsed.speaker_title
            if parsed.speaker_intro:
                merged["speaker_intro"] = parsed.speaker_intro
            if parsed.organizer:
                merged["organizer"] = parsed.organizer
            if parsed.activity_type:
                merged["activity_type"] = parsed.activity_type
            if parsed.summary:
                merged["description"] = parsed.summary

            merged.update(
                {
                    "campus": parsed.campus,
                    "bonus_type": parsed.bonus_type,
                    "bonus_detail": parsed.bonus_detail,
                    "llm_confidence": parsed.confidence,
                    "llm_pending": parsed.needs_review,
                    "llm_error": None,
                }
            )
            return merged

        merged.update(
            {
                "llm_pending": outcome.pending,
                "llm_error": outcome.error,
            }
        )
        return merged

    def fetch(self, service, source: dict) -> list[dict]:
        source_id = source.get("cache_key") or source["id"]
        llm_enabled = is_activity_llm_enabled()
        llm_max_per_source = int(
            os.getenv(
                "ACTIVITY_LLM_MAX_WEBSITE_ITEMS_PER_SOURCE",
                os.getenv("ACTIVITY_LLM_MAX_ARTICLES_PER_SOURCE", "2"),
            )
        )
        llm_attempted = 0

        with service._lock:
            cached = service._source_cache.get(source_id)
            if cached and service._is_cache_entry_fresh(cached["timestamp"]):
                service._update_source_status(
                    source,
                    ok=True,
                    item_count=len(cached["items"]),
                    cached=True,
                )
                return cached["items"]

        soup = BeautifulSoup(service._fetch_html(source["url"]), "html.parser")

        item_selectors = merge_selectors(
            source["selectors"].get("list"),
            FALLBACK_ITEM_SELECTORS,
            custom_first=True,
        )
        title_selectors = merge_selectors(
            source["selectors"].get("title"),
            FALLBACK_TITLE_SELECTORS,
            custom_first=False,
        )
        date_selectors = merge_selectors(
            source["selectors"].get("date"),
            FALLBACK_DATE_SELECTORS,
            custom_first=False,
        )

        items = []
        for node in service._pick_nodes(soup, item_selectors):
            title, anchor = service._extract_title_and_anchor(node, title_selectors)
            if not anchor or not title or title in SKIP_TITLES:
                continue

            href = clean_text(anchor.get("href"))
            if not href:
                continue

            detail_url = urljoin(source["url"], href)
            activity_time = strip_prefix(
                service._pick_text(node, [".news_sj .textcon", ".sj", ".time"]),
                ["时间：", "时 间：", "时间:", "时   间：", "时 间:"],
            )
            speaker = strip_prefix(
                service._pick_text(node, [".news_zj .textcon", ".zjr", ".speaker .textcon"]),
                ["主讲人：", "主讲人:", "报告人：", "报告人:"],
            )
            location = strip_prefix(
                service._pick_text(node, [".news_dd .textcon", ".dd", ".location"]),
                ["地点：", "地点:", "地 点：", "地   点：", "地 点:"],
            )
            date_text = service._pick_text(node, date_selectors) or clean_text(node.get_text(" ", strip=True))
            activity_date = (
                to_iso_date(activity_time)
                or to_iso_date(date_text)
                or to_iso_date(title)
                or to_iso_date(detail_url)
            )
            if not activity_date:
                continue

            description = clean_text(node.get_text(" ", strip=True))
            description = description if description and description != title else None

            activity = {
                "id": build_activity_id(source["id"], detail_url, title),
                "title": title,
                "college_id": source["id"],
                "college_name": source["name"],
                "activity_type": "讲座",
                "speaker": speaker,
                "speaker_title": None,
                "speaker_intro": None,
                "activity_date": activity_date,
                "activity_time": activity_time,
                "location": location,
                "organizer": source["name"],
                "description": description,
                "cover_image": None,
                "source_url": detail_url,
                "registration_required": False,
                "registration_link": None,
                "source_type": source["source_type"],
                "raw_date_text": date_text,
            }

            if llm_enabled and llm_attempted < llm_max_per_source:
                llm_attempted += 1
                detail_title, detail_text = self._fetch_detail_text(service, detail_url)
                if detail_title and detail_title != title:
                    activity["title"] = detail_title
                llm_text = detail_text or clean_text(node.get_text("\n", strip=True))
                activity = self._apply_llm_result(
                    title=activity["title"],
                    description=description,
                    detail_text=llm_text,
                    activity=activity,
                )
                if activity is None:
                    continue

            items.append(activity)

        deduped = dedupe_exact_items(items)
        service._store_cached_source_items(source_id, deduped)
        service._update_source_status(
            source,
            ok=True,
            item_count=len(deduped),
            cached=False,
        )
        return deduped
