from __future__ import annotations

import re
import os
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from sqlalchemy import bindparam, text

from core.activity_llm import is_activity_llm_enabled, parse_activity_with_llm
from core.non_activity_classifier import classify_record_bucket
from core.print import print_info

from .common import (
    DELETED_STATUS,
    WECHAT_ARTICLE_LOOKBACK_DAYS,
    build_activity_id,
    clean_text,
    dedupe_exact_items,
    extract_labeled_text,
    to_iso_date_with_default_year,
)


class WechatActivityAdapter:
    channel = "wechat"

    def _article_body_text(self, article: dict) -> str:
        html_or_text = article.get("content_html") or article.get("content") or ""
        if not html_or_text:
            return ""
        if "<" in html_or_text and ">" in html_or_text:
            try:
                soup = BeautifulSoup(html_or_text, "html.parser")
                text_value = soup.get_text("\n", strip=True)
            except Exception:
                text_value = html_or_text
        else:
            text_value = html_or_text

        normalized_lines = []
        for line in text_value.replace("\r", "\n").splitlines():
            cleaned_line = clean_text(line)
            if cleaned_line:
                normalized_lines.append(cleaned_line)
        return "\n".join(normalized_lines).strip()

    def _extract_registration_link_from_article(self, article: dict) -> str | None:
        content_html = article.get("content_html") or ""
        if not content_html:
            return None
        try:
            soup = BeautifulSoup(content_html, "html.parser")
        except Exception:
            return None

        for link in soup.find_all("a", href=True):
            text_value = clean_text(link.get_text(" ", strip=True))
            if any(keyword in text_value for keyword in ["报名", "预约", "注册链接"]):
                return link["href"]
        return None

    def _guess_activity_type(self, text_value: str) -> str:
        candidate = clean_text(text_value)
        if "论坛" in candidate:
            return "论坛"
        if "研讨会" in candidate:
            return "研讨会"
        if "学术报告" in candidate or "报告" in candidate:
            return "学术报告"
        if "训练营" in candidate:
            return "训练营"
        if "分享会" in candidate:
            return "分享会"
        return "讲座"

    def _extract_detail_text_value(self, text_value: str, patterns: list[str]) -> str | None:
        return extract_labeled_text(
            text_value,
            inline_patterns=patterns,
            labels=[],
        )

    def extract_article_metadata(self, article: dict) -> dict:
        body_text = self._article_body_text(article)

        publish_year = None
        publish_time = article.get("publish_time")
        if isinstance(publish_time, int):
            try:
                publish_year = datetime.fromtimestamp(publish_time).year
            except Exception:
                publish_year = None

        # 预处理 body_text：合并被换行打断的日期（如 "4\n月10日" → "4月10日"）
        body_text_processed = re.sub(r"(\d)\n(?=月)", r"\1", body_text)
        time_label_pattern = (
            r"(?:(?:活动时间|讲座时间)\s*(?:[:：]\s*|(?=[0-9０-９一二三四五六日天上下早中晚今明本周星期（(]))|"
            r"时\s*间\s*(?:[:：]\s*|(?=[0-9０-９一二三四五六日天上下早中晚今明本周星期（(]))"
            r")"
        )

        speaker = extract_labeled_text(
            body_text_processed,
            inline_patterns=[r"(?:主讲人|报告人|分享人|嘉宾)\s*[:：]?\s*([^\n]+)"],
            labels=["主讲人", "报告人", "分享人", "嘉宾"],
            stop_labels=["活动时间", "讲座时间", "时间", "活动地点", "讲座地点", "地点", "主讲人简介"],
        )
        activity_time = extract_labeled_text(
            body_text_processed,
            inline_patterns=[
                rf"{time_label_pattern}([^\n]{{2,50}}?)(?=\n|$|活动地点|讲座地点|地\s*点|活动形式|形式|主讲人|报告人|分享人|嘉宾|主讲人简介)",
                rf"{time_label_pattern}([^\n]+)",
            ],
            labels=["活动时间", "讲座时间", "时间"],
            stop_labels=["活动地点", "讲座地点", "地点", "活动形式", "形式", "主讲人", "报告人", "分享人", "嘉宾", "主讲人简介"],
        )
        location = extract_labeled_text(
            body_text_processed,
            inline_patterns=[
                r"(?:活动地点|讲座地点|地\s*点)\s*(?:[:：]\s*)?([^\n]{2,40}?)(?=\n|$|活动形式|形式|主讲人|报告人|分享人|嘉宾|时\s*间|主讲人简介)",
                r"(?:活动地点|讲座地点|地\s*点)\s*(?:[:：]\s*)?([^\n]+)",
            ],
            labels=["活动地点", "讲座地点", "地点"],
            stop_labels=["活动形式", "形式", "主讲人", "报告人", "分享人", "嘉宾", "时间", "活动时间", "讲座时间", "主讲人简介"],
        )

        activity_date = (
            to_iso_date_with_default_year(activity_time, publish_year)
            or to_iso_date_with_default_year(clean_text(article.get("title")), publish_year)
            or to_iso_date_with_default_year(clean_text(article.get("description")), publish_year)
            or to_iso_date_with_default_year(body_text[:1200], publish_year)
        )

        return {
            "body_text": body_text,
            "body_text_processed": body_text_processed,
            "publish_year": publish_year,
            "speaker": speaker,
            "activity_time": activity_time,
            "location": location,
            "activity_date": activity_date,
            "registration_link": self._extract_registration_link_from_article(article),
            "summary": clean_text(article.get("description")) or clean_text(body_text[:280]) or clean_text(article.get("title")),
        }

    def _is_activity_candidate(self, service, title: str, description: str, body_text: str) -> bool:
        config = service._load_config()
        keyword_config = config.get("crawl_config", {}).get("keywords", {})
        include_keywords = keyword_config.get("primary", []) + keyword_config.get("series", []) + [
            "分享会",
            "宣讲会",
            "训练营",
            "活动预告",
            "讲座预告",
        ]
        exclude_keywords = keyword_config.get("exclude", [])

        text_value = f"{title}\n{description}\n{body_text}".lower()
        has_include = any(keyword.lower() in text_value for keyword in include_keywords if keyword)
        has_exclude = any(keyword.lower() in text_value for keyword in exclude_keywords if keyword)

        if has_exclude and not has_include:
            return False
        return has_include

    def _article_to_activity(self, service, source: dict, article: dict, *, use_llm: bool = True) -> dict | None:
        description = clean_text(article.get("description"))
        title = clean_text(article.get("title"))
        extracted = self.extract_article_metadata(article)
        body_text = extracted["body_text"]

        if not self._is_activity_candidate(service, title, description, body_text):
            return None

        publish_time = article.get("publish_time")
        publish_year = extracted["publish_year"]
        body_text_processed = extracted["body_text_processed"]
        speaker = extracted["speaker"]
        activity_time = extracted["activity_time"]
        location = extracted["location"]
        activity_date = extracted["activity_date"]
        registration_link = extracted["registration_link"]
        summary = extracted["summary"]
        llm_extra = {}

        if use_llm and is_activity_llm_enabled():
            print_info(f"LLM 解析公众号文章: {title[:40]}")
            outcome = parse_activity_with_llm(
                title=title,
                description=description,
                body_text=body_text_processed,
                publish_year=publish_year,
            )
            if outcome.result:
                parsed = outcome.result
                if not parsed.is_activity:
                    return None
                activity_date = parsed.activity_date or activity_date
                activity_time = parsed.activity_time or activity_time
                speaker = parsed.speaker or speaker
                location = parsed.location or location
                summary = parsed.summary or summary
                llm_extra = {
                    "speaker_title": parsed.speaker_title,
                    "speaker_intro": parsed.speaker_intro,
                    "activity_type": parsed.activity_type,
                    "organizer": parsed.organizer,
                    "campus": parsed.campus,
                    "bonus_type": parsed.bonus_type,
                    "bonus_detail": parsed.bonus_detail,
                    "llm_confidence": parsed.confidence,
                    "llm_pending": parsed.needs_review,
                    "llm_error": None,
                }
                print_info(
                    "LLM 解析完成: "
                    f"is_activity={parsed.is_activity} "
                    f"date={parsed.activity_date} "
                    f"confidence={parsed.confidence}"
                )
            elif outcome.pending:
                llm_extra = {
                    "llm_pending": True,
                    "llm_error": outcome.error,
                }

        if not activity_date:
            if llm_extra.get("llm_pending"):
                return None
            return None

        organizer = llm_extra.get("organizer") or source["name"]
        activity_type = llm_extra.get("activity_type") or self._guess_activity_type(title)
        speaker_title = llm_extra.get("speaker_title")
        speaker_intro = llm_extra.get("speaker_intro")
        record_bucket, non_activity_reason = classify_record_bucket(
            title=title,
            description=description,
            body_text=body_text_processed,
            activity_time=activity_time,
            location=location,
            activity_date=activity_date,
            publish_time=publish_time,
        )

        return {
            "id": build_activity_id(source["cache_key"], article.get("url") or article.get("id"), title),
            "title": title,
            "college_id": source["id"],
            "college_name": source["name"],
            "activity_type": activity_type,
            "speaker": speaker,
            "speaker_title": speaker_title,
            "speaker_intro": speaker_intro,
            "activity_date": activity_date,
            "activity_time": activity_time,
            "location": location,
            "organizer": organizer,
            "description": summary,
            "cover_image": article.get("pic_url") or None,
            "source_url": article.get("url"),
            "registration_required": bool(registration_link),
            "registration_link": registration_link,
            "source_type": source["source_type"],
            "source_channel": "wechat",
            "mp_name": source.get("mp_name"),
            "raw_date_text": activity_time or description,
            "publish_time": publish_time,
            "record_bucket": record_bucket,
            "non_activity_reason": non_activity_reason,
            **llm_extra,
        }

    def fetch(self, service, source: dict) -> list[dict]:
        cache_key = source.get("cache_key") or source["id"]
        llm_enabled = is_activity_llm_enabled()
        llm_max_per_source = int(os.getenv("ACTIVITY_LLM_MAX_ARTICLES_PER_SOURCE", "2"))
        llm_attempted = 0

        with service._lock:
            cached = service._source_cache.get(cache_key)
            if cached and service._is_cache_entry_fresh(cached["timestamp"]):
                service._update_source_status(
                    source,
                    ok=True,
                    item_count=len(cached["items"]),
                    cached=True,
                )
                return cached["items"]

        engine = service._get_wechat_db_engine()
        if engine is None:
            service._update_source_status(
                source,
                ok=False,
                error="wechat_db_unavailable",
            )
            return []

        with engine.connect() as conn:
            feed_rows = conn.execute(
                text("SELECT id FROM feeds WHERE mp_name = :mp_name"),
                {"mp_name": source.get("mp_name")},
            ).mappings().all()
            feed_ids = [row["id"] for row in feed_rows]
            if not feed_ids:
                items = []
            else:
                publish_after = int((datetime.now() - timedelta(days=WECHAT_ARTICLE_LOOKBACK_DAYS)).timestamp())
                stmt = (
                    text(
                        """
                        SELECT id, mp_id, title, pic_url, url, description, status, publish_time, content, content_html
                        FROM articles
                        WHERE mp_id IN :feed_ids
                          AND status != :deleted_status
                          AND publish_time >= :publish_after
                        ORDER BY publish_time DESC
                        LIMIT 200
                        """
                    )
                    .bindparams(bindparam("feed_ids", expanding=True))
                )
                articles = conn.execute(
                    stmt,
                    {
                        "feed_ids": feed_ids,
                        "deleted_status": DELETED_STATUS,
                        "publish_after": publish_after,
                    },
                ).mappings().all()

                items = []
                for article in articles:
                    use_llm = llm_enabled and llm_attempted < llm_max_per_source
                    if use_llm:
                        llm_attempted += 1
                    activity = self._article_to_activity(service, source, article, use_llm=use_llm)
                    if activity:
                        items.append(activity)

        deduped = dedupe_exact_items(items)
        service._store_cached_source_items(cache_key, deduped)
        service._update_source_status(
            source,
            ok=True,
            item_count=len(deduped),
            cached=False,
        )
        return deduped
