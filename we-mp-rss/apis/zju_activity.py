from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status as fast_status

from apis.base import ErrorCategory, categorized_error_response, error_response, success_response
from core.activity_service import activity_service


router = APIRouter(tags=["浙大活动日历"])
service = activity_service


@router.get("/activities", summary="获取浙大活动列表")
async def list_activities(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    college_id: Optional[str] = Query(None, description="学院或来源 ID"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    student_view: bool = Query(False, description="是否启用本科生预览视角"),
    sort_by: str = Query("date", description="排序方式：date 或 relevance"),
    upcoming_only: bool = Query(False, description="是否只返回未来活动"),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    refresh: bool = Query(False, description="是否强制刷新缓存"),
):
    try:
        data = service.list_activities(
            start_date=start_date,
            end_date=end_date,
            college_id=college_id,
            keyword=keyword,
            student_view=student_view,
            sort_by=sort_by,
            upcoming_only=upcoming_only,
            page=page,
            limit=limit,
            refresh=refresh,
        )
        return success_response(data)
    except Exception as exc:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=categorized_error_response(code=50001, message=f"获取活动列表失败: {exc}", category=ErrorCategory.INTERNAL),
        )


@router.get("/activities/search", summary="搜索浙大活动")
async def search_activities(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
):
    return await list_activities(keyword=q, page=page, limit=limit)


@router.get("/activities/{activity_id}", summary="获取浙大活动详情")
async def get_activity(activity_id: str):
    try:
        activity = service.get_activity(activity_id)
        if not activity:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=categorized_error_response(code=40404, message="活动不存在", category=ErrorCategory.NOT_FOUND),
            )
        return success_response(activity)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=categorized_error_response(code=50001, message=f"获取活动详情失败: {exc}", category=ErrorCategory.INTERNAL),
        )


@router.get("/colleges", summary="获取浙大活动来源列表")
async def get_colleges():
    try:
        return success_response(service.get_colleges())
    except Exception as exc:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=categorized_error_response(code=50001, message=f"获取来源列表失败: {exc}", category=ErrorCategory.INTERNAL),
        )
