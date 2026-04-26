#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.activity_sources.common import extract_campus
from core.activity_sources.wechat import WechatActivityAdapter


def is_missing(value: str | None) -> bool:
    return value is None or not str(value).strip()


def is_invalid_date(value: str | None) -> bool:
    if not value or not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return True
    year, month, day = map(int, value.split("-"))
    return not (1 <= month <= 12 and 1 <= day <= 31)


def looks_like_activity_time(value: str | None) -> bool:
    text = (value or "").strip()
    if not text or len(text) > 60:
        return False
    if any(mark in text for mark in "。！？；"):
        return False
    if not re.search(r"\d", text):
        return False
    return bool(
        re.search(
            r"(月|日|周|星期|\d{1,2}\s*[:：]\s*\d{2}|上午|下午|晚上|~|-|－|—)",
            text,
        )
    )


def looks_like_location(value: str | None) -> bool:
    text = (value or "").strip()
    if not text or len(text) > 80:
        return False
    if any(mark in text for mark in "。！？；"):
        return False
    return True


def load_targets(con: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT *
        FROM activities
        WHERE source_channel = 'wechat'
          AND (
            activity_time IS NULL OR trim(activity_time) = ''
            OR location IS NULL OR trim(location) = ''
            OR activity_date IS NULL OR trim(activity_date) = ''
            OR length(activity_date) != 10
            OR substr(activity_date, 5, 1) != '-'
            OR substr(activity_date, 8, 1) != '-'
          )
        ORDER BY publish_time DESC, fetched_at DESC
    """
    rows = con.execute(query).fetchall()
    if limit is not None:
        return rows[:limit]
    return rows


def find_article(con: sqlite3.Connection, activity: sqlite3.Row) -> sqlite3.Row | None:
    by_url = con.execute(
        """
        SELECT id, mp_id, title, pic_url, url, description, publish_time, content, content_html
        FROM articles
        WHERE url = ?
        ORDER BY publish_time DESC
        LIMIT 1
        """,
        (activity["source_url"],),
    ).fetchone()
    if by_url:
        return by_url

    return con.execute(
        """
        SELECT id, mp_id, title, pic_url, url, description, publish_time, content, content_html
        FROM articles
        WHERE title = ?
        ORDER BY publish_time DESC
        LIMIT 1
        """,
        (activity["title"],),
    ).fetchone()


def build_updates(activity: sqlite3.Row, extracted: dict) -> dict:
    updates = {}

    parsed_time = extracted.get("activity_time")
    parsed_location = extracted.get("location")

    if is_missing(activity["activity_time"]) and looks_like_activity_time(parsed_time):
        updates["activity_time"] = extracted["activity_time"]
    if is_missing(activity["location"]) and looks_like_location(parsed_location):
        updates["location"] = extracted["location"]
    if is_missing(activity["registration_link"]) and extracted.get("registration_link"):
        updates["registration_link"] = extracted["registration_link"]
        updates["registration_required"] = 1
    if is_missing(activity["description"]) and extracted.get("summary"):
        updates["description"] = extracted["summary"]

    existing_date = activity["activity_date"]
    new_date = extracted.get("activity_date")
    if new_date and not is_invalid_date(new_date) and (is_invalid_date(existing_date) or is_missing(existing_date)):
        updates["activity_date"] = new_date

    campus = activity["campus"]
    if is_missing(campus):
        resolved_campus = extract_campus(updates.get("location") or activity["location"])
        if resolved_campus:
            updates["campus"] = resolved_campus

    raw_date_text = activity["raw_date_text"]
    if is_missing(raw_date_text) and updates.get("activity_time"):
        updates["raw_date_text"] = updates["activity_time"]

    return updates


def apply_updates(con: sqlite3.Connection, activity_id: str, updates: dict) -> None:
    assignments = ", ".join(f"{column} = ?" for column in updates)
    values = list(updates.values()) + [activity_id]
    con.execute(f"UPDATE activities SET {assignments} WHERE id = ?", values)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing wechat activity fields from stored article content.")
    parser.add_argument("--db", default=str(ROOT / "data" / "db.db"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write", action="store_true", help="Persist updates to the database.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    adapter = WechatActivityAdapter()

    targets = load_targets(con, args.limit)
    updated = 0
    matched = 0
    skipped = 0

    for activity in targets:
        article = find_article(con, activity)
        if not article:
            skipped += 1
            if args.verbose:
                print(f"SKIP no article: {activity['title']}")
            continue

        matched += 1
        extracted = adapter.extract_article_metadata(dict(article))
        updates = build_updates(activity, extracted)
        if not updates:
            if args.verbose:
                print(f"UNCHANGED {activity['title']}")
            continue

        updated += 1
        if args.verbose:
            print(f"UPDATE {activity['title']}")
            for key, value in updates.items():
                print(f"  {key}: {value}")
        if args.write:
            apply_updates(con, activity["id"], updates)

    if args.write:
        con.commit()

    print(
        f"targets={len(targets)} matched_articles={matched} updated={updated} "
        f"skipped={skipped} mode={'write' if args.write else 'dry-run'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
