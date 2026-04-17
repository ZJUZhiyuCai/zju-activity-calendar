from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from apis.auth import router as auth_router
from apis.mps import router as wx_router
from apis.sys_info import router as sys_info_router
from apis.zju_activity import router as zju_activity_router
from core.config import API_BASE, VERSION, cfg
from core.db import DB
from core.runtime_bootstrap import ensure_admin_user
from core.activity_scraper import scrape_and_persist, SCRAPE_INTERVAL_MINUTES
from core.content_filler import fill_one_article
from core.mp_sync_scheduler import (
    sync_all_mps,
    MP_SYNC_INTERVAL_MINUTES,
)
from core.task.task import TaskScheduler

PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "static"
FRONTEND_DIST_DIR = STATIC_DIR / "calendar"
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"
FRONTEND_DIST_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="ZJU Activity Calendar API",
    description="浙大活动日历的数据接口与公众号采集服务",
    version="1.0.0",
    docs_url="/api/docs",  # 指定文档路径
    redoc_url="/api/redoc",  # 指定Redoc路径
    # 指定OpenAPI schema路径
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {
            "name": "认证",
            "description": "用户认证相关接口",
        }
    ],
    swagger_ui_parameters={
        "persistAuthorization": True,
        "withCredentials": True,
    }
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_scheduler = TaskScheduler()


@app.on_event("startup")
async def ensure_tables():
    DB.create_tables()
    ensure_admin_user(DB)

    # 启动定时采集：首次立即执行，之后按间隔重复
    import threading
    threading.Thread(target=scrape_and_persist, daemon=True).start()

    # 构造 cron 表达式：<60 分钟用分钟字段，>=60 分钟用小时字段
    if SCRAPE_INTERVAL_MINUTES < 60:
        cron_expr = f"*/{SCRAPE_INTERVAL_MINUTES} * * * *"
    else:
        hours = max(SCRAPE_INTERVAL_MINUTES // 60, 1)
        cron_expr = f"0 */{hours} * * *"

    _scheduler.add_cron_job(
        func=scrape_and_persist,
        cron_expr=cron_expr,
        job_id="activity_scraper",
        tag="活动定时采集",
    )

    # 添加文章内容补全任务：每分钟执行一次
    _scheduler.add_cron_job(
        func=fill_one_article,
        cron_expr="* * * * *",  # 每分钟
        job_id="content_filler",
        tag="文章内容补全",
    )

    # 添加公众号自动同步任务
    if MP_SYNC_INTERVAL_MINUTES < 60:
        mp_sync_cron = f"*/{MP_SYNC_INTERVAL_MINUTES} * * * *"
    else:
        mp_sync_hours = max(MP_SYNC_INTERVAL_MINUTES // 60, 1)
        mp_sync_cron = f"0 */{mp_sync_hours} * * *"

    _scheduler.add_cron_job(
        func=sync_all_mps,
        cron_expr=mp_sync_cron,
        job_id="mp_sync_scheduler",
        tag="公众号自动同步",
    )
    print(f"[Startup] 公众号自动同步已启动，间隔: {MP_SYNC_INTERVAL_MINUTES}分钟")

    _scheduler.start()


@app.on_event("shutdown")
async def shutdown_scheduler():
    _scheduler.shutdown(wait=False)


@app.middleware("http")
async def add_custom_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Version"] = VERSION
    response.headers["X-Powered-By"] = "ZJU Activity Calendar"
    response.headers["Server"] = cfg.get("server.name", "zju-activity-calendar")
    return response
# 创建API路由分组
api_router = APIRouter(prefix=f"{API_BASE}")
api_router.include_router(auth_router)
api_router.include_router(wx_router)
api_router.include_router(sys_info_router)
api_router.include_router(zju_activity_router)
# 注册API路由分组
app.include_router(api_router)

# 静态文件服务配置
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/calendar", StaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="calendar")
from core.res.avatar import files_dir
app.mount("/files", StaticFiles(directory=files_dir), name="files")
# app.mount("/docs", StaticFiles(directory="./data/docs"), name="docs")
def serve_frontend_index():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)

    return JSONResponse(
        status_code=503,
        content={
            "error": "frontend_not_built",
            "message": "Calendar frontend build not found. Run `npm run build` in frontend/.",
        },
    )

@app.get("/",tags=['默认'],include_in_schema=False)
async def serve_root(request: Request):
    """默认打开学生端活动日历。"""
    return serve_frontend_index()


@app.get("/{path:path}",tags=['默认'],include_in_schema=False)
async def serve_frontend_app(request: Request, path: str):
    """为非 API 路径返回学生端日历入口。"""
    if path.startswith(("api", "static", "files", "calendar")):
        return JSONResponse(status_code=404, content={"error": "Not Found"})

    return serve_frontend_index()
