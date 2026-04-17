from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from sqlalchemy import bindparam, text

from .common import (
    DELETED_STATUS,
    WECHAT_ARTICLE_LOOKBACK_DAYS,
    build_activity_id,
    clean_text,
    dedupe_exact_items,
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
        for pattern in patterns:
            match = re.search(pattern, text_value, flags=re.IGNORECASE)
            if not match:
                continue
            return clean_text(match.group(1))
        return None

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

    def _article_to_activity(self, service, source: dict, article: dict) -> dict | None:
        body_text = self._article_body_text(article)
        description = clean_text(article.get("description"))
        title = clean_text(article.get("title"))

        if not self._is_activity_candidate(service, title, description, body_text):
            return None

        publish_year = None
        publish_time = article.get("publish_time")
        if isinstance(publish_time, int):
            try:
                publish_year = datetime.fromtimestamp(publish_time).year
            except Exception:
                publish_year = None

        # 预处理 body_text：合并被换行打断的日期（如 "4\n月10日" → "4月10日"）
        body_text_processed = re.sub(r'(\d)\n(?=月)', r'\1', body_text)

        speaker = self._extract_detail_text_value(
            body_text_processed,
            [r"(?:主讲人|报告人|分享人|嘉宾)\s*[:：]\s*([^\n]+)"],
        )
        activity_time = self._extract_detail_text_value(
            body_text_processed,
            [
                r"(?:活动时间|讲座时间|时\s*间)\s*[:：]\s*([^\n]{2,50}?)(?=\n|$|活动地点|地点:|主讲人|嘉宾)",
                r"(?:活动时间|讲座时间|时\s*间)\s*[:：]\s*([^\n]+)",
            ],
        )
        location = self._extract_detail_text_value(
            body_text_processed,
            [
                r"(?:活动地点|讲座地点|地\s*点)\s*[:：]\s*([^\n]{2,40}?)(?=\n|$|活动形式|形式:|主讲人|时间)",
                r"(?:活动地点|讲座地点|地\s*点)\s*[:：]\s*([^\n]+)",
            ],
        )

        activity_date = (
            to_iso_date_with_default_year(activity_time, publish_year)
            or to_iso_date_with_default_year(title, publish_year)
            or to_iso_date_with_default_year(description, publish_year)
            or to_iso_date_with_default_year(body_text[:1200], publish_year)
        )
        if not activity_date:
            return None

        registration_link = self._extract_registration_link_from_article(article)
        summary = description or clean_text(body_text[:280]) or title

        return {
            "id": build_activity_id(source["cache_key"], article.get("url") or article.get("id"), title),
            "title": title,
            "college_id": source["id"],
            "college_name": source["name"],
            "activity_type": self._guess_activity_type(title),
            "speaker": speaker,
            "speaker_title": None,
            "speaker_intro": None,
            "activity_date": activity_date,
            "activity_time": activity_time,
            "location": location,
            "organizer": source["name"],
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
        }

    def fetch(self, service, source: dict) -> list[dict]:
        cache_key = source.get("cache_key") or source["id"]

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
                    activity = self._article_to_activity(service, source, article)
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
