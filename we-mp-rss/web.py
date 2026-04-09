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


@app.on_event("startup")
async def ensure_tables():
    DB.create_tables()
    ensure_admin_user(DB)


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
