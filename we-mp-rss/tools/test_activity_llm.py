#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def html_to_text(value: str) -> str:
    if "<" not in value or ">" not in value:
        return value
    soup = BeautifulSoup(value, "html.parser")
    return soup.get_text("\n", strip=True)


def fetch_article(db_path: Path, article_id: str | None) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    if article_id:
        row = con.execute(
            "SELECT id, title, description, publish_time, content, content_html FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    else:
        row = con.execute(
            """
            SELECT id, title, description, publish_time, content, content_html
            FROM articles
            WHERE length(coalesce(content_html, content, '')) > 500
            ORDER BY publish_time DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        raise SystemExit("article not found")
    return dict(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test LLM activity extraction on one article.")
    parser.add_argument("--article-id", help="articles.id to parse")
    parser.add_argument("--db", default=str(ROOT / "data" / "db.db"))
    args = parser.parse_args()

    load_env(ROOT / ".env")
    from core.activity_llm import parse_activity_with_llm

    article = fetch_article(Path(args.db), args.article_id)
    publish_year = None
    if isinstance(article.get("publish_time"), int):
        publish_year = datetime.fromtimestamp(article["publish_time"]).year

    outcome = parse_activity_with_llm(
        title=article.get("title") or "",
        description=article.get("description") or "",
        body_text=html_to_text(article.get("content_html") or article.get("content") or ""),
        publish_year=publish_year,
    )

    payload = {
        "article_id": article["id"],
        "title": article["title"],
        "pending": outcome.pending,
        "error": outcome.error,
        "result": outcome.result.model_dump() if outcome.result else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if outcome.result else 1


if __name__ == "__main__":
    raise SystemExit(main())
