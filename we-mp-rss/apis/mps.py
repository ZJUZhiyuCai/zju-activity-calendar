from __future__ import annotations

import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func

from core.auth import get_maintenance_user
from core.config import cfg
from core.db import DB
from core.queue import TaskQueue
from core.res import save_avatar_locally
from core.wx import WxGather, search_Biz
from driver.wxarticle import WXArticleFetcher
from jobs.article import UpdateArticle

from .base import ErrorCategory, categorized_error_response, error_response, success_response


router = APIRouter(prefix="/mps", tags=["公众号采集"])


def _serialize_feed(feed, stats: Optional[dict] = None):
    stats = stats or {}
    return {
        "id": feed.id,
        "mp_name": feed.mp_name,
        "mp_cover": feed.mp_cover,
        "mp_intro": feed.mp_intro,
        "status": feed.status,
        "faker_id": feed.faker_id,
        "sync_time": feed.sync_time,
        "update_time": feed.update_time,
        "created_at": feed.created_at.isoformat() if feed.created_at else None,
        "updated_at": feed.updated_at.isoformat() if feed.updated_at else None,
        "article_count": stats.get("article_count", 0),
        "last_article_publish_time": stats.get("last_article_publish_time"),
    }


def _load_feed_stats(session, feed_ids: list[str]) -> dict[str, dict]:
    if not feed_ids:
        return {}

    from core.models.article import Article

    rows = (
        session.query(
            Article.mp_id.label("mp_id"),
            func.count(Article.id).label("article_count"),
            func.max(Article.publish_time).label("last_article_publish_time"),
        )
        .filter(Article.mp_id.in_(feed_ids))
        .group_by(Article.mp_id)
        .all()
    )
    return {
        row.mp_id: {
            "article_count": int(row.article_count or 0),
            "last_article_publish_time": row.last_article_publish_time,
        }
        for row in rows
    }


def _queue_sync(feed, *, start_page: int = 0, end_page: int = 1):
    queue_info = TaskQueue.get_queue_info()
    if not queue_info.get("is_running"):
        return False

    TaskQueue.add_task(
        WxGather().Model().get_Articles,
        faker_id=feed.faker_id,
        Mps_id=feed.id,
        CallBack=UpdateArticle,
        start_page=start_page,
        MaxPage=end_page,
        Mps_title=feed.mp_name,
        task_name=feed.mp_name,
    )
    return True


@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str,
    limit: int = Query(10, ge=1, le=20),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_maintenance_user),
):
    try:
        result = search_Biz(kw, limit=limit, offset=offset)
        return success_response(
            {
                "list": result.get("list") if result else [],
                "page": {"limit": limit, "offset": offset},
                "total": result.get("total") if result else 0,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=categorized_error_response(
                code=50001,
                message=f"搜索公众号失败，请重新扫码授权: {exc}",
                category=ErrorCategory.EXTERNAL_DEPENDENCY,
            ),
        )


@router.get("", summary="获取公众号列表")
async def get_mps(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    status_filter: Optional[int] = Query(None, alias="status"),
    current_user: dict = Depends(get_maintenance_user),
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        query = session.query(Feed)
        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
        if status_filter is not None:
            query = query.filter(Feed.status == status_filter)

        total = query.count()
        feeds = (
            query.order_by(Feed.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        stats_map = _load_feed_stats(session, [feed.id for feed in feeds])
        return success_response(
            {
                "list": [_serialize_feed(feed, stats_map.get(feed.id)) for feed in feeds],
                "page": {"limit": limit, "offset": offset, "total": total},
                "total": total,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=categorized_error_response(code=50001, message=f"获取公众号列表失败: {exc}", category=ErrorCategory.INTERNAL),
        )
    finally:
        session.close()


@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp(mp_id: str, current_user: dict = Depends(get_maintenance_user)):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="公众号不存在"),
            )
        stats_map = _load_feed_stats(session, [mp.id])
        return success_response(_serialize_feed(mp, stats_map.get(mp.id)))
    finally:
        session.close()


@router.post("/by_article", summary="通过文章链接解析公众号信息")
async def get_mp_by_article(
    url: str = Query(..., min_length=1),
    current_user: dict = Depends(get_maintenance_user),
):
    fetcher = WXArticleFetcher()
    try:
        info = await fetcher.async_get_article_content(url)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=categorized_error_response(code=40401, message="未解析到公众号信息", category=ErrorCategory.NOT_FOUND),
            )
        return success_response(info)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=categorized_error_response(code=50001, message="请输入正确的公众号文章链接", category=ErrorCategory.VALIDATION),
        )
    finally:
        try:
            fetcher.Close()
        except Exception:
            pass


@router.post("", summary="添加公众号")
async def add_mp(
    mp_name: str = Body("", max_length=255),
    mp_cover: Optional[str] = Body(None, max_length=255),
    mp_id: Optional[str] = Body(None, max_length=255),
    article_url: Optional[str] = Body(None, max_length=1000),
    avatar: Optional[str] = Body(None, max_length=500),
    mp_intro: Optional[str] = Body(None, max_length=255),
    current_user: dict = Depends(get_maintenance_user),
):
    if not mp_id and article_url:
        fetcher = WXArticleFetcher()
        try:
            article_info = await fetcher.async_get_article_content(article_url)
            biz = article_info.get("mp_info", {}).get("biz")
            if biz:
                mp_id = biz
            if not mp_name or mp_name == "string":
                mp_name = article_info.get("mp_info", {}).get("mp_name") or mp_name
            if not avatar:
                avatar = article_info.get("mp_info", {}).get("logo") or avatar
            if not mp_intro:
                mp_intro = article_info.get("description") or mp_intro
        finally:
            try:
                fetcher.Close()
            except Exception:
                pass

    if not mp_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=categorized_error_response(code=40003, message="缺少公众号名称", category=ErrorCategory.VALIDATION),
        )

    if not mp_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=categorized_error_response(code=40001, message="缺少公众号标识", category=ErrorCategory.VALIDATION),
        )

    session = DB.get_session()
    try:
        from core.models.feed import Feed

        now = datetime.now()
        try:
            decoded_id = base64.b64decode(mp_id).decode("utf-8")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=categorized_error_response(code=40002, message=f"公众号标识格式错误: {exc}", category=ErrorCategory.VALIDATION),
            )
        local_avatar_path = save_avatar_locally(avatar) if avatar else (mp_cover or "")

        feed = session.query(Feed).filter(Feed.faker_id == mp_id).first()
        created = False

        if feed:
            feed.mp_name = mp_name
            feed.mp_cover = local_avatar_path
            feed.mp_intro = mp_intro
            feed.updated_at = now
        else:
            feed = Feed(
                id=f"MP_WXS_{decoded_id}",
                mp_name=mp_name,
                mp_cover=local_avatar_path,
                mp_intro=mp_intro,
                status=1,
                created_at=now,
                updated_at=now,
                faker_id=mp_id,
                update_time=0,
                sync_time=0,
            )
            session.add(feed)
            created = True

        session.commit()

        queued = False
        if created:
            queued = _queue_sync(feed, start_page=0, end_page=int(cfg.get("max_page", "2")))

        return success_response(
            {
                **_serialize_feed(feed),
                "sync_queued": queued,
                "worker_running": TaskQueue.get_queue_info().get("is_running", False),
            },
            message=(
                "公众号添加成功并已加入同步队列"
                if queued
                else "公众号添加成功，但当前未检测到同步 worker"
            ) if created else "公众号信息已更新",
        )
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=categorized_error_response(code=50001, message=f"添加公众号失败: {exc}", category=ErrorCategory.INTERNAL),
        )
    finally:
        session.close()


@router.post("/{mp_id}/sync", summary="手动同步公众号文章")
@router.get("/update/{mp_id}", summary="手动同步公众号文章（兼容旧路径）")
async def sync_mp(
    mp_id: str,
    start_page: int = Query(0, ge=0),
    end_page: int = Query(1, ge=1),
    current_user: dict = Depends(get_maintenance_user),
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=categorized_error_response(code=40401, message="请选择一个公众号", category=ErrorCategory.NOT_FOUND),
            )

        queued = _queue_sync(mp, start_page=start_page, end_page=end_page)
        if not queued:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=categorized_error_response(code=50301, message="同步 worker 未运行，请使用 `python main.py --mode worker` 或 `--mode all`", category=ErrorCategory.SERVICE_STATE),
            )
        return success_response(
            {
                "id": mp.id,
                "mp_name": mp.mp_name,
                "start_page": start_page,
                "end_page": end_page,
                "queued": True,
            },
            message="已加入采集队列",
        )
    finally:
        session.close()


@router.delete("/{mp_id}", summary="删除公众号")
async def delete_mp(mp_id: str, current_user: dict = Depends(get_maintenance_user)):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="公众号不存在"),
            )

        session.delete(mp)
        session.commit()
        return success_response({"id": mp_id}, message="公众号删除成功")
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message=f"删除公众号失败: {exc}"),
        )
    finally:
        session.close()


@router.put("/{mp_id}", summary="更新公众号信息")
async def update_mp(
    mp_id: str,
    mp_name: Optional[str] = Body(None),
    mp_cover: Optional[str] = Body(None),
    mp_intro: Optional[str] = Body(None),
    status_value: Optional[int] = Body(None, alias="status"),
    current_user: dict = Depends(get_maintenance_user),
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="公众号不存在"),
            )

        if mp_name is not None:
            mp.mp_name = mp_name
        if mp_cover is not None:
            mp.mp_cover = mp_cover
        if mp_intro is not None:
            mp.mp_intro = mp_intro
        if status_value is not None:
            mp.status = status_value

        mp.updated_at = datetime.now()
        session.commit()
        return success_response(_serialize_feed(mp), message="更新成功")
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message=f"更新公众号失败: {exc}"),
        )
    finally:
        session.close()
