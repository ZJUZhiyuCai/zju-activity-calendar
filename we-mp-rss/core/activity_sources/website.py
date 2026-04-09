from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import (
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

    def fetch(self, service, source: dict) -> list[dict]:
        source_id = source.get("cache_key") or source["id"]

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

            items.append(
                {
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
            )

        deduped = dedupe_exact_items(items)
        service._store_cached_source_items(source_id, deduped)
        service._update_source_status(
            source,
            ok=True,
            item_count=len(deduped),
            cached=False,
        )
        return deduped
