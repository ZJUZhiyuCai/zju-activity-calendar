"""定时采集活动数据并持久化到数据库。"""

from __future__ import annotations

import os
import time
import threading

from core.app_logging import log_event
from core.print import print_info, print_warning, print_error


# 采集间隔（分钟），默认 60
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))

_scrape_lock = threading.Lock()


def scrape_and_persist() -> None:
    """遍历所有来源，抓取活动并写入 activities 表。"""
    if not _scrape_lock.acquire(blocking=False):
        print_warning("上一轮采集尚未完成，跳过本次")
        return

    try:
        _do_scrape()
    finally:
        _scrape_lock.release()


def _do_scrape() -> None:
    from core.activity_service import activity_service
    from core.db import DB
    from core.models.activity import Activity
    from core.models.non_activity_record import NonActivityRecord

    service = activity_service
    now_ts = int(time.time())
    collected = []

    # 遍历所有渠道的所有来源
    for channel in service._source_registry.iter_channels():
        build_sources = service._source_registry.get_service_source_builder(
            service, channel
        )
        for source in build_sources():
            try:
                items = service._fetch_items_for_source(source)
                collected.extend(items)
            except Exception as exc:
                service._update_source_status(source, ok=False, error=str(exc))
                print_warning(f"采集失败: {source['id']} -> {exc}")
                log_event(
                    "warning",
                    "scraper source failed",
                    source_id=source["id"],
                    error=str(exc),
                )

    # 去重 + 校验
    collected = service._dedupe_activities(collected)
    valid_items, _ = service._validate_activities(collected)

    # 写入数据库
    session = DB.get_session()
    upserted = 0
    try:
        for item in valid_items:
            row = session.query(Activity).filter(Activity.id == item["id"]).first()
            if row is None:
                row = Activity(id=item["id"])
                session.add(row)

            def prefer_incoming(field: str):
                incoming = item.get(field)
                if incoming is None:
                    return getattr(row, field)
                if isinstance(incoming, str) and not incoming.strip():
                    return getattr(row, field)
                return incoming

            row.title = item.get("title")
            row.college_id = item.get("college_id")
            row.college_name = item.get("college_name")
            row.activity_type = item.get("activity_type")
            row.activity_date = item.get("activity_date")
            row.activity_time = prefer_incoming("activity_time")
            row.campus = prefer_incoming("campus")
            row.location = prefer_incoming("location")
            row.speaker = prefer_incoming("speaker")
            row.speaker_title = prefer_incoming("speaker_title")
            row.speaker_intro = prefer_incoming("speaker_intro")
            row.organizer = prefer_incoming("organizer")
            row.description = prefer_incoming("description")
            row.cover_image = prefer_incoming("cover_image")
            row.source_url = item.get("source_url")
            row.source_type = item.get("source_type")
            row.source_channel = item.get("source_channel", "website")
            row.raw_date_text = prefer_incoming("raw_date_text")
            row.mp_name = item.get("mp_name")
            row.publish_time = item.get("publish_time")
            row.registration_required = 1 if item.get("registration_required") or row.registration_required else 0
            row.registration_link = prefer_incoming("registration_link")
            row.bonus_type = prefer_incoming("bonus_type")
            row.bonus_detail = prefer_incoming("bonus_detail")
            row.llm_pending = 1 if item.get("llm_pending") else 0
            if "llm_error" in item:
                row.llm_error = item.get("llm_error")
            else:
                row.llm_error = prefer_incoming("llm_error")
            row.llm_confidence = (
                str(item.get("llm_confidence")) if item.get("llm_confidence") is not None else row.llm_confidence
            )
            row.record_bucket = item.get("record_bucket") or "activity"
            row.non_activity_reason = item.get("non_activity_reason") if row.record_bucket == "non_activity" else None
            row.fetched_at = now_ts

            if row.record_bucket == "non_activity":
                archived = session.query(NonActivityRecord).filter(
                    NonActivityRecord.activity_id == item["id"]
                ).first()
                if archived is None:
                    archived = NonActivityRecord(activity_id=item["id"])
                    session.add(archived)
                archived.title = item.get("title")
                archived.college_id = item.get("college_id")
                archived.college_name = item.get("college_name")
                archived.source_url = item.get("source_url")
                archived.source_type = item.get("source_type")
                archived.source_channel = item.get("source_channel", "website")
                archived.mp_name = item.get("mp_name")
                archived.publish_time = item.get("publish_time")
                archived.activity_date = item.get("activity_date")
                archived.activity_time = item.get("activity_time")
                archived.location = item.get("location")
                archived.description = item.get("description")
                archived.cover_image = item.get("cover_image")
                archived.classification_reason = item.get("non_activity_reason")
                archived.body_preview = (item.get("description") or "")[:1000]
                archived.archived_at = now_ts
            upserted += 1

        session.commit()
    except Exception as exc:
        session.rollback()
        print_error(f"活动写入数据库失败: {exc}")
        log_event("error", "scraper db write failed", error=str(exc))
        return

    print_info(f"采集完成: 写入/更新 {upserted} 条活动")
    log_event(
        "info",
        "scraper completed",
        upserted=upserted,
        total_collected=len(collected),
        total_valid=len(valid_items),
    )
