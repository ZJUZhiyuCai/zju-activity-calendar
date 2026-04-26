#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.wx import search_Biz
from core.wx.base import WxGather
from jobs.article import UpdateArticle


@dataclass(frozen=True)
class TargetAccount:
    mp_name: str
    college_id: str
    college_name: str


TARGET_ACCOUNTS = [
    TargetAccount("浙大文学院团委", "lit", "文学院"),
    TargetAccount("浙大经院青年", "cec", "经济学院"),
    TargetAccount("浙江大学医学院团委", "cmm", "医学院"),
    TargetAccount("公小管", "spa", "公共管理学院"),
    TargetAccount("EE生辉", "ee", "电气工程学院"),
    TargetAccount("求是外院青年", "sis", "外国语学院"),
    TargetAccount("信电青年", "isee", "信息与电子工程学院"),
    TargetAccount("ZJU能小源", "doe", "能源工程学院"),
    TargetAccount("浙大机械青年", "me", "机械工程学院"),
    TargetAccount("媒大媒小", "cmic", "传媒与国际文化学院"),
    TargetAccount("ZJU微计录", "cs", "计算机科学与技术学院"),
]


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def _normalize_name(value: str | None) -> str:
    return "".join((value or "").strip().lower().split())


def _candidate_name(item: dict[str, Any]) -> str:
    for key in ("nickname", "nick_name", "name", "user_name", "alias"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _candidate_faker_id(item: dict[str, Any]) -> str:
    for key in ("fakeid", "fake_id", "faker_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _candidate_avatar(item: dict[str, Any]) -> str | None:
    for key in ("round_head_img", "head_img", "avatar", "logo"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _candidate_intro(item: dict[str, Any]) -> str | None:
    for key in ("signature", "brief", "description", "intro"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    seen = set()
    for item in _iter_dicts(payload):
        faker_id = _candidate_faker_id(item)
        name = _candidate_name(item)
        if not faker_id or not name:
            continue
        key = (faker_id, name)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "mp_name": name,
                "faker_id": faker_id,
                "avatar": _candidate_avatar(item),
                "mp_intro": _candidate_intro(item),
                "raw": item,
            }
        )
    return candidates


def _normalize_faker_id(raw_value: str) -> tuple[str, str]:
    try:
        decoded = base64.b64decode(raw_value).decode("utf-8")
        if decoded.isdigit():
            return raw_value, decoded
    except Exception:
        pass
    if raw_value.isdigit():
        encoded = base64.b64encode(raw_value.encode("utf-8")).decode("utf-8")
        return encoded, raw_value
    raise ValueError(f"Unrecognized fakeid format: {raw_value}")


def choose_candidate(target: TargetAccount, payload: dict[str, Any]) -> dict[str, Any] | None:
    candidates = extract_candidates(payload)
    exact = [item for item in candidates if _normalize_name(item["mp_name"]) == _normalize_name(target.mp_name)]
    if exact:
        return exact[0]

    target_name = _normalize_name(target.mp_name)
    college_name = _normalize_name(target.college_name)
    fuzzy = [
        item
        for item in candidates
        if target_name in _normalize_name(item["mp_name"])
        or college_name in _normalize_name(item["mp_name"])
    ]
    if fuzzy:
        return fuzzy[0]
    return None


def upsert_feed(db_path: Path, target: TargetAccount, candidate: dict[str, Any], *, verbose: bool) -> dict[str, str]:
    faker_id_encoded, decoded_id = _normalize_faker_id(candidate["faker_id"])
    feed_id = f"MP_WXS_{decoded_id}"
    now = datetime.now()

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT id FROM feeds WHERE id = ? OR faker_id = ?", (feed_id, faker_id_encoded)).fetchone()

    if row:
        con.execute(
            """
            UPDATE feeds
            SET mp_name = ?, mp_cover = COALESCE(?, mp_cover), mp_intro = COALESCE(?, mp_intro),
                status = 1, updated_at = ?
            WHERE id = ?
            """,
            (target.mp_name, candidate.get("avatar"), candidate.get("mp_intro"), now.isoformat(sep=" "), row["id"]),
        )
        action = "updated"
    else:
        con.execute(
            """
            INSERT INTO feeds (
                id, mp_name, mp_cover, mp_intro, status, sync_time, update_time,
                created_at, updated_at, faker_id
            ) VALUES (?, ?, ?, ?, 1, 0, 0, ?, ?, ?)
            """,
            (
                feed_id,
                target.mp_name,
                candidate.get("avatar") or "",
                candidate.get("mp_intro") or "",
                now.isoformat(sep=" "),
                now.isoformat(sep=" "),
                faker_id_encoded,
            ),
        )
        action = "created"
    con.commit()
    con.close()

    if verbose:
        print(f"{action.upper()} {target.mp_name} -> {feed_id}")
    return {"id": feed_id, "faker_id": faker_id_encoded}


def sync_articles(feed_id: str, faker_id: str, mp_name: str, *, pages: int, verbose: bool) -> None:
    if verbose:
        print(f"SYNC {mp_name} pages={pages}")
    WxGather().Model().get_Articles(
        faker_id=faker_id,
        Mps_id=feed_id,
        Mps_title=mp_name,
        CallBack=UpdateArticle,
        start_page=0,
        MaxPage=pages,
        interval=1,
        Gather_Content=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Search, onboard, and sync target college WeChat accounts.")
    parser.add_argument("--db", default=str(ROOT / "data" / "db.db"))
    parser.add_argument("--pages", type=int, default=4, help="How many pages to sync per account; 4 pages ~= 20 articles.")
    parser.add_argument("--search-limit", type=int, default=8)
    parser.add_argument("--write", action="store_true", help="Persist feeds to the database.")
    parser.add_argument("--sync", action="store_true", help="Sync articles after feed upsert.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    onboarded = 0
    matched = 0

    for target in TARGET_ACCOUNTS:
        if args.verbose:
            print(f"\n## {target.mp_name}")
        try:
            payload = search_Biz(target.mp_name, limit=args.search_limit, offset=0)
        except Exception as exc:
            print(f"SEARCH_FAILED {target.mp_name}: {exc}")
            continue

        candidate = choose_candidate(target, payload or {})
        if not candidate:
            print(f"NO_MATCH {target.mp_name}")
            continue
        matched += 1

        if args.verbose:
            print(f"MATCH {target.mp_name} -> {candidate['mp_name']} fakeid={candidate['faker_id']}")

        if not args.write:
            continue

        feed = upsert_feed(db_path, target, candidate, verbose=args.verbose)
        onboarded += 1

        if args.sync:
            try:
                sync_articles(feed["id"], feed["faker_id"], target.mp_name, pages=args.pages, verbose=args.verbose)
            except Exception as exc:
                print(f"SYNC_FAILED {target.mp_name}: {exc}")

    print(
        f"targets={len(TARGET_ACCOUNTS)} matched={matched} "
        f"onboarded={onboarded} mode={'write' if args.write else 'dry-run'} sync={args.sync}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
