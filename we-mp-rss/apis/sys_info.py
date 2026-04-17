import platform
import time
import sys
from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query, status as fast_status
from fastapi.responses import JSONResponse
from typing import Dict, Any
from core.auth import get_current_user, get_maintenance_user
from .base import ErrorCategory, categorized_error_response, success_response, error_response
from core.activity_service import activity_service
from core.config import cfg, API_BASE
from core.queue import ContentTaskQueue, TaskQueue
from driver.success import getLoginInfo, getStatus

router = APIRouter(prefix="/sys", tags=["系统信息"])


def _product_snapshot():
    return {
        "name": cfg.get("server.web_name", "浙大活动日历"),
        "positioning": "面向浙大本科生的活动预览工具",
        "primary_scene": "30 秒内看懂这周值得参加的讲座和活动",
        "frontend_entry": "/",
        "activity_api": f"{API_BASE}/activities",
    }


def get_docker_version():
    try:
        with open("./docker_version.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "未知"


# 记录服务器启动时间
_START_TIME = time.time()


def _get_activity_snapshot() -> dict:
    summary = activity_service.get_source_status_summary()
    runtime_health = activity_service.get_runtime_health()

    if not summary.get("generated_at"):
        result = activity_service.list_activities(limit=1)
        runtime_health = activity_service.get_runtime_health()
        return {
            "status": runtime_health.get("status"),
            "generated_at": result.get("generated_at"),
            "last_success_sync_at": result.get("last_success_sync_at"),
            "source_status": result.get("source_status"),
            "source_metrics": result.get("source_metrics"),
            "validation": result.get("validation"),
            "freshness": result.get("freshness"),
        }

    return {
        "status": runtime_health.get("status"),
        "generated_at": summary.get("generated_at"),
        "last_success_sync_at": summary.get("last_success_sync_at"),
        "source_status": summary,
        "source_metrics": [],
        "validation": {"valid_count": 0, "dropped_count": 0, "dropped_by_source": {}, "invalid_examples": []},
        "freshness": summary.get("freshness"),
    }


@router.get("/base_info", summary="常规信息")
async def get_base_info() -> Dict[str, Any]:
    try:
        from .ver import API_VERSION
        from core.config import VERSION as CORE_VERSION

        base_info = {
            'api_version': API_VERSION,
            'docker_version': get_docker_version(),
            'core_version': CORE_VERSION,
            'product': _product_snapshot(),
            "ui": {
                "name": cfg.get("server.name", ""),
                "web_name": cfg.get("server.web_name", "浙大活动日历"),
            }
        }
        return success_response(data=base_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取信息失败: {str(e)}"
        )


@router.get("/health/live", summary="存活检查")
async def health_live() -> Dict[str, Any]:
    return success_response(
        data={
            "status": "alive",
            "timestamp": time.time(),
        }
    )


@router.get("/health/ready", summary="就绪检查")
async def health_ready() -> Dict[str, Any]:
    try:
        snapshot = _get_activity_snapshot()
        if snapshot["status"] in {"cold", "degraded"}:
            return JSONResponse(
                status_code=503,
                content=categorized_error_response(code=50302, message="活动数据未就绪", category=ErrorCategory.SERVICE_STATE, data=snapshot),
            )

        return success_response(data=snapshot)
    except Exception as e:
        return error_response(
            code=50003,
            message=f"就绪检查失败: {str(e)}"
        )


@router.get("/source_status", summary="来源状态汇总")
async def get_source_status() -> Dict[str, Any]:
    try:
        return success_response(data=_get_activity_snapshot().get("source_status", {}))
    except Exception as e:
        return error_response(
            code=50004,
            message=f"获取来源状态失败: {str(e)}"
        )


@router.get("/config_summary", summary="配置边界摘要")
async def get_config_summary(
    current_user: dict = Depends(get_maintenance_user)
) -> Dict[str, Any]:
    try:
        from core.config import cfg as runtime_cfg

        return success_response(data=runtime_cfg.get_runtime_config_summary())
    except Exception as e:
        return categorized_error_response(
            code=50008,
            message=f"获取配置摘要失败: {str(e)}",
            category=ErrorCategory.CONFIG,
        )


@router.get("/source_metrics", summary="来源级统计")
async def get_source_metrics() -> Dict[str, Any]:
    try:
        snapshot = _get_activity_snapshot()
        if not snapshot.get("source_metrics"):
            snapshot = activity_service.list_activities(limit=1)
        return success_response(
            data={
                "generated_at": snapshot.get("generated_at"),
                "freshness": snapshot.get("freshness"),
                "items": snapshot.get("source_metrics", []),
                "validation": snapshot.get("validation"),
            }
        )
    except Exception as e:
        return error_response(
            code=50005,
            message=f"获取来源级统计失败: {str(e)}"
        )


@router.post("/sources/{source_id}/refresh", summary="按来源手动刷新")
async def refresh_source(
    source_id: str,
    source_channel: str = Query("website", description="来源通道：website 或 wechat"),
    current_user: dict = Depends(get_maintenance_user),
) -> Dict[str, Any]:
    try:
        if source_channel not in {"website", "wechat"}:
            raise HTTPException(
                status_code=fast_status.HTTP_400_BAD_REQUEST,
                detail=categorized_error_response(
                    code=40011,
                    message="source_channel 仅支持 website 或 wechat",
                    category=ErrorCategory.VALIDATION,
                ),
            )

        return success_response(activity_service.refresh_source(source_id=source_id, source_channel=source_channel))
    except HTTPException:
        raise
    except LookupError:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=categorized_error_response(
                code=40411,
                message="来源不存在",
                category=ErrorCategory.NOT_FOUND,
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=categorized_error_response(
                code=40012,
                message=f"来源刷新参数错误: {exc}",
                category=ErrorCategory.VALIDATION,
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=categorized_error_response(
                code=50009,
                message=f"来源刷新失败: {exc}",
                category=ErrorCategory.INTERNAL,
            ),
        )


def _resolve_queue(queue_name: str):
    if queue_name == "content":
        return ContentTaskQueue
    return TaskQueue


@router.get("/queue_status", summary="队列状态")
async def get_queue_status(
    current_user: dict = Depends(get_maintenance_user)
) -> Dict[str, Any]:
    try:
        return success_response(
            data={
                "main_queue": TaskQueue.get_management_snapshot(),
                "content_queue": ContentTaskQueue.get_management_snapshot(),
            }
        )
    except Exception as e:
        return error_response(
            code=50006,
            message=f"获取队列状态失败: {str(e)}"
        )


@router.get("/queue_history", summary="队列历史")
async def get_queue_history(
    queue_name: str = "main",
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(get_maintenance_user),
) -> Dict[str, Any]:
    try:
        queue_handle = _resolve_queue(queue_name)
        return success_response(
            data={
                "queue": queue_name,
                **queue_handle.get_history_page(page=page, page_size=page_size),
            }
        )
    except Exception as e:
        return error_response(
            code=50007,
            message=f"获取队列历史失败: {str(e)}"
        )

from core.resource import get_system_resources
from core.content_filler import get_filler_status, fill_one_article


@router.get("/content_filler/status", summary="内容补全服务状态")
async def get_content_filler_status(
    current_user: dict = Depends(get_maintenance_user)
) -> Dict[str, Any]:
    """获取文章内容补全服务的状态

    Returns:
        包含以下字段:
        - is_rate_limited: 是否处于风控暂停期
        - last_run_at: 上次运行时间
        - success_count: 成功次数
        - fail_count: 失败次数
        - rate_limited_count: 触发风控次数
    """
    try:
        return success_response(data=get_filler_status())
    except Exception as e:
        return error_response(
            code=50010,
            message=f"获取内容补全状态失败: {str(e)}"
        )


@router.post("/content_filler/trigger", summary="手动触发内容补全")
async def trigger_content_filler(
    current_user: dict = Depends(get_maintenance_user)
) -> Dict[str, Any]:
    """手动触发一次内容补全任务"""
    try:
        fill_one_article()
        return success_response(message="内容补全任务已触发")
    except Exception as e:
        return error_response(
            code=50011,
            message=f"触发内容补全失败: {str(e)}"
        )
@router.get("/resources", summary="获取系统资源使用情况")
async def system_resources(
    current_user: dict = Depends(get_maintenance_user)
) -> Dict[str, Any]:
    """获取系统资源使用情况
    
    Returns:
        BaseResponse格式的资源使用信息，包括:
        - cpu: CPU使用率(%)
        - memory: 内存使用情况
        - disk: 磁盘使用情况
    """
    try:
        resources_info = get_system_resources()
        resources_info["queue"] = TaskQueue.get_queue_info()
        return success_response(data=resources_info)
    except Exception as e:
        return error_response(
            code=50002,
            message=f"获取系统资源失败: {str(e)}"
        )
from core.article_lax import get_article_info
from .ver import API_VERSION
from core.base import VERSION as CORE_VERSION,LATEST_VERSION
@router.get("/info", summary="获取系统信息")
async def get_system_info(
    current_user: dict = Depends(get_maintenance_user)
) -> Dict[str, Any]:
    """获取当前系统的各种信息
    
    Returns:
        BaseResponse格式的系统信息，包括:
        - os: 操作系统信息
        - python_version: Python版本
        - uptime: 服务器运行时间(秒)
        - system: 系统详细信息
    """
    try:
      
        from driver.token import get as get_val
        # 获取系统信息
        system_info = {
            'os': {
                'name': platform.system(),
                'version': platform.version(),
                'docker_version': get_docker_version(),
                'release': platform.release(),
            },
            'python_version': sys.version,
            'uptime': round(time.time() - _START_TIME, 2),
            'system': {
                'node': platform.node(),
                'machine': platform.machine(),
                'processor': platform.processor(),
            },
            'api_version': API_VERSION,
            'core_version': CORE_VERSION,
            'latest_version':LATEST_VERSION,
            'need_update':CORE_VERSION != LATEST_VERSION,
            'product': _product_snapshot(),
            "wx":{
                'token':get_val('token',''),
                'expiry_time':get_val('expiry.expiry_time','') if getStatus() else "",
                "info":getLoginInfo(),
                "login":getStatus(),
            },
            "article":get_article_info(),
            'queue':TaskQueue.get_queue_info(),
        }
        return success_response(data=system_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取系统信息失败: {str(e)}"
        )
