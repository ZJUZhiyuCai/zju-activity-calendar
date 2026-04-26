#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import cfg
from core.content_filler import fetch_article_content, update_article_content
from core.print import print_error, print_info, print_warning


TARGET_MP_NAMES = [
    "浙大文学院团委",
    "浙大经院青年",
    "浙江大学医学院团委",
    "公小管",
    "EE生辉",
    "求是外院青年",
    "信电青年",
    "ZJU能小源",
    "浙大机械青年",
    "媒大媒小",
    "ZJU微计录",
]


def iter_pending_articles(engine, mp_names: Iterable[str], limit: int | None) -> list[dict]:
    placeholders = ", ".join(f":name_{idx}" for idx, _ in enumerate(mp_names))
    params = {f"name_{idx}": name for idx, name in enumerate(mp_names)}
    query = f"""
        SELECT a.id, a.mp_id, f.mp_name, a.title, a.url, a.publish_time
        FROM articles a
        JOIN feeds f ON f.id = a.mp_id
        WHERE f.mp_name IN ({placeholders})
          AND (a.content IS NULL OR trim(a.content) = '')
          AND a.url IS NOT NULL
        ORDER BY a.publish_time DESC
    """
    if limit is not None:
        query += " LIMIT :limit"
        params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill article content for the newly onboarded college WeChat accounts.")
    parser.add_argument("--interval", type=int, default=30, help="Minimum seconds between two article fetches.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max article count to process this run.")
    parser.add_argument("--loop", action="store_true", help="Keep polling for new empty articles until interrupted.")
    args = parser.parse_args()

    engine = create_engine(cfg.get("db", "sqlite:///data/db.db"))
    total_success = 0
    total_fail = 0

    while True:
        pending = iter_pending_articles(engine, TARGET_MP_NAMES, args.limit)
        if not pending:
            print_info("目标公众号暂无待补全文章")
            if args.loop:
                time.sleep(max(args.interval, 5))
                continue
            break

        print_info(f"准备补全 {len(pending)} 篇目标公众号文章，限速 {args.interval}s/篇")
        for article in pending:
            started_at = time.time()
            print_info(f"抓取正文: [{article['mp_name']}] {article['title'][:60]}")
            result = fetch_article_content(article["url"])
            if result.get("success"):
                update_article_content(
                    engine,
                    article["id"],
                    result.get("content", ""),
                    result.get("content_html", ""),
                )
                total_success += 1
                print_info(
                    f"补全成功: {article['id']} length={result.get('length', 0)} "
                    f"success={total_success} fail={total_fail}"
                )
            else:
                total_fail += 1
                error = result.get("error", "unknown")
                print_warning(
                    f"补全失败: {article['id']} error={error} "
                    f"success={total_success} fail={total_fail}"
                )

            elapsed = time.time() - started_at
            sleep_for = max(args.interval - elapsed, 0)
            if sleep_for > 0:
                time.sleep(sleep_for)

        if not args.loop:
            break

    print_info(f"运行结束: success={total_success} fail={total_fail}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print_error("用户中断了正文补全任务")
        raise
