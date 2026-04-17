"""公众号自动同步调度器

功能：
1. 定时遍历所有配置的公众号
2. 将同步任务加入队列
3. 支持配置同步间隔和每批最大同步数量
"""

from __future__ import annotations

import os
import time
import threading
from datetime import datetime
from typing import Optional

from core.db import DB
from core.print import print_info, print_warning, print_error
from core.queue import TaskQueue
from core.wx import WxGather
from jobs.article import UpdateArticle

# 同步间隔（分钟），默认 30 分钟
MP_SYNC_INTERVAL_MINUTES = int(os.getenv("MP_SYNC_INTERVAL_MINUTES", "30"))
# 每次同步最大公众号数量，默认 5 个（避免队列堆积）
MP_SYNC_MAX_PER_BATCH = int(os.getenv("MP_SYNC_MAX_PER_BATCH", "5"))
# 每页抓取的文章页数，默认 1 页（每页 5 篇）
MP_SYNC_MAX_PAGE = int(os.getenv("MP_SYNC_MAX_PAGE", "1"))

_sync_lock = threading.Lock()


def sync_all_mps() -> None:
    """遍历所有公众号，将同步任务加入队列"""
    if not _sync_lock.acquire(blocking=False):
        print_warning("[MP Sync] 上一轮同步尚未完成，跳过本次")
        return

    try:
        _do_sync_all_mps()
    finally:
        _sync_lock.release()


def _do_sync_all_mps() -> None:
    """执行同步逻辑"""
    from core.models.feed import Feed

    session = DB.get_session()
    try:
        # 获取所有启用的公众号，按最后同步时间排序（优先同步很久没有同步的）
        feeds = (
            session.query(Feed)
            .filter(Feed.status == 1)
            .order_by(Feed.sync_time.asc())
            .limit(MP_SYNC_MAX_PER_BATCH)
            .all()
        )

        if not feeds:
            print_info("[MP Sync] 没有需要同步的公众号")
            return

        queued_count = 0
        for feed in feeds:
            # 检查队列是否已满
            queue_info = TaskQueue.get_queue_info()
            if queue_info.get("pending_count", 0) >= 10:
                print_warning(f"[MP Sync] 队列已满，暂停添加任务")
                break

            # 检查该公众号最近是否已同步（避免过于频繁）
            if feed.sync_time:
                last_sync = datetime.fromtimestamp(feed.sync_time)
                minutes_since_sync = (datetime.now() - last_sync).total_seconds() / 60
                if minutes_since_sync < MP_SYNC_INTERVAL_MINUTES:
                    print_info(f"[MP Sync] {feed.mp_name} 最近 {minutes_since_sync:.0f} 分钟前已同步，跳过")
                    continue

            # 添加同步任务到队列
            try:
                TaskQueue.add_task(
                    WxGather().Model().get_Articles,
                    faker_id=feed.faker_id,
                    Mps_id=feed.id,
                    CallBack=UpdateArticle,
                    start_page=0,
                    MaxPage=MP_SYNC_MAX_PAGE,
                    Mps_title=feed.mp_name,
                    task_name=f"同步-{feed.mp_name}",
                )
                queued_count += 1
                print_info(f"[MP Sync] 已添加同步任务: {feed.mp_name}")
            except Exception as e:
                print_error(f"[MP Sync] 添加任务失败 {feed.mp_name}: {e}")

        if queued_count > 0:
            print_info(f"[MP Sync] 本次共添加 {queued_count} 个同步任务")

    except Exception as exc:
        print_error(f"[MP Sync] 同步失败: {exc}")
    finally:
        session.close()


def get_sync_status() -> dict:
    """获取同步状态（用于 API 查询）"""
    from core.models.feed import Feed

    session = DB.get_session()
    try:
        total = session.query(Feed).filter(Feed.status == 1).count()

        # 获取最近同步的公众号
        recent_feeds = (
            session.query(Feed)
            .filter(Feed.status == 1)
            .order_by(Feed.sync_time.desc())
            .limit(5)
            .all()
        )

        return {
            "total_mps": total,
            "interval_minutes": MP_SYNC_INTERVAL_MINUTES,
            "max_per_batch": MP_SYNC_MAX_PER_BATCH,
            "max_page": MP_SYNC_MAX_PAGE,
            "recent_syncs": [
                {
                    "mp_name": f.mp_name,
                    "sync_time": f.sync_time,
                    "sync_time_str": datetime.fromtimestamp(f.sync_time).isoformat() if f.sync_time else None,
                }
                for f in recent_feeds
            ],
        }
    finally:
        session.close()
