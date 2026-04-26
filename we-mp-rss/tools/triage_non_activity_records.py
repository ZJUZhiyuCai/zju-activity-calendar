#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.non_activity_classifier import classify_record_bucket
from core.activity_sources.wechat import WechatActivityAdapter


def fetch_article(con: sqlite3.Connection, activity: sqlite3.Row) -> sqlite3.Row | None:
    row = con.execute(
        """
        SELECT id, title, description, publish_time, content, content_html, url
        FROM articles
        WHERE url = ?
        ORDER BY publish_time DESC
        LIMIT 1
        """,
        (activity["source_url"],),
    ).fetchone()
    if row:
        return row
    return con.execute(
        """
        SELECT id, title, description, publish_time, content, content_html, url
        FROM articles
        WHERE title = ?
        ORDER BY publish_time DESC
        LIMIT 1
        """,
        (activity["title"],),
    ).fetchone()


def ensure_non_activity_table(con: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in con.execute("PRAGMA table_info(activities)").fetchall()
    }
    if "record_bucket" not in existing_columns:
        con.execute("ALTER TABLE activities ADD COLUMN record_bucket TEXT DEFAULT 'activity'")
    if "non_activity_reason" not in existing_columns:
        con.execute("ALTER TABLE activities ADD COLUMN non_activity_reason TEXT")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS non_activity_records (
            activity_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            college_id TEXT,
            college_name TEXT,
            source_url TEXT,
            source_type TEXT,
            source_channel TEXT,
            mp_name TEXT,
            publish_time INTEGER,
            activity_date TEXT,
            activity_time TEXT,
            location TEXT,
            description TEXT,
            cover_image TEXT,
            classification_reason TEXT,
            body_preview TEXT,
            archived_at INTEGER
        )
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark and archive obvious non-activity records.")
    parser.add_argument("--db", default=str(ROOT / "data" / "db.db"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    ensure_non_activity_table(con)
    adapter = WechatActivityAdapter()
    now_ts = int(time.time())

    query = """
        SELECT *
        FROM activities
        WHERE source_channel = 'wechat'
          AND (record_bucket IS NULL OR record_bucket != 'non_activity')
        ORDER BY publish_time DESC, fetched_at DESC
    """
    rows = con.execute(query).fetchall()
    if args.limit is not None:
        rows = rows[: args.limit]

    marked = 0
    for activity in rows:
        article = fetch_article(con, activity)
        extracted_body = {}
        body_text = ""
        if article:
            extracted_body = adapter.extract_article_metadata(dict(article))
            body_text = extracted_body.get("body_text_processed") or extracted_body.get("body_text") or ""

        bucket, reason = classify_record_bucket(
            title=activity["title"],
            description=activity["description"],
            body_text=body_text,
            activity_time=activity["activity_time"],
            location=activity["location"],
            activity_date=activity["activity_date"],
            publish_time=activity["publish_time"],
        )
        if bucket != "non_activity":
            continue

        marked += 1
        if args.verbose:
            print(f"MARK {activity['title']} -> {reason}")

        if not args.write:
            continue

        con.execute(
            """
            UPDATE activities
            SET record_bucket = 'non_activity', non_activity_reason = ?
            WHERE id = ?
            """,
            (reason, activity["id"]),
        )
        con.execute(
            """
            INSERT INTO non_activity_records (
                activity_id, title, college_id, college_name, source_url, source_type,
                source_channel, mp_name, publish_time, activity_date, activity_time,
                location, description, cover_image, classification_reason, body_preview, archived_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                title=excluded.title,
                college_id=excluded.college_id,
                college_name=excluded.college_name,
                source_url=excluded.source_url,
                source_type=excluded.source_type,
                source_channel=excluded.source_channel,
                mp_name=excluded.mp_name,
                publish_time=excluded.publish_time,
                activity_date=excluded.activity_date,
                activity_time=excluded.activity_time,
                location=excluded.location,
                description=excluded.description,
                cover_image=excluded.cover_image,
                classification_reason=excluded.classification_reason,
                body_preview=excluded.body_preview,
                archived_at=excluded.archived_at
            """,
            (
                activity["id"],
                activity["title"],
                activity["college_id"],
                activity["college_name"],
                activity["source_url"],
                activity["source_type"],
                activity["source_channel"],
                activity["mp_name"],
                activity["publish_time"],
                activity["activity_date"],
                activity["activity_time"],
                activity["location"],
                activity["description"],
                activity["cover_image"],
                reason,
                body_text[:1000],
                now_ts,
            ),
        )

    if args.write:
        con.commit()

    print(f"scanned={len(rows)} marked={marked} mode={'write' if args.write else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
