from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_maintenance_user,
)
from core.config import cfg, set_config
from driver.base import WX_API
from driver.success import getLoginInfo, getStatus

from .base import ErrorCategory, categorized_error_response, error_response, success_response


router = APIRouter(prefix="/auth", tags=["认证"])


def auth_success(data):
    if not data:
        print("\n登录失败，请检查上述错误信息")
        return

    print("\n登录结果:")
    print(f"Token: {data['token']}")
    set_config("token", data["token"])
    cfg.reload()


@router.get("/qr/code", summary="获取登录二维码")
async def get_qrcode(current_user=Depends(get_maintenance_user)):
    return success_response(WX_API.GetCode(auth_success))


@router.get("/qr/image", summary="获取登录二维码图片")
async def qr_image(current_user=Depends(get_maintenance_user)):
    return success_response(WX_API.GetHasCode())


@router.get("/qr/status", summary="获取扫描状态")
async def qr_status(current_user=Depends(get_maintenance_user)):
    return success_response(WX_API.QrStatus())


@router.get("/qr/over", summary="扫码完成")
async def qr_success(current_user=Depends(get_maintenance_user)):
    return success_response(WX_API.Close())


@router.get("/session", summary="获取公众号登录会话状态")
async def get_session(current_user=Depends(get_maintenance_user)):
    if hasattr(WX_API, "get_session_info"):
        session_info = WX_API.get_session_info()
    else:
        login_info = getLoginInfo() or {}
        session_info = {
            "is_logged_in": bool(getStatus()),
            "token": login_info.get("token", ""),
            "cookies": {},
            "cookies_str": login_info.get("cookie", ""),
            "expiry": login_info.get("expiry"),
            "login_info": login_info,
        }
    return success_response(
        {
            **session_info,
            "qr_code_exists": WX_API.GetHasCode(),
            "auth_mode": "web" if bool(cfg.get("server.auth_web", False)) else "api",
        }
    )


def _build_token_payload(user):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/login", summary="用户登录")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=categorized_error_response(code=40101, message="用户名或密码错误", category=ErrorCategory.AUTH),
        )
    return success_response(_build_token_payload(user))


@router.post("/token", summary="获取Token")
async def get_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=categorized_error_response(code=40101, message="用户名或密码错误", category=ErrorCategory.AUTH),
        )
    return _build_token_payload(user)


@router.post("/logout", summary="用户注销")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"code": 0, "message": "注销成功"}


@router.post("/refresh", summary="刷新Token")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user["username"]},
        expires_delta=access_token_expires,
    )
    return success_response(
        {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    )


@router.get("/verify", summary="验证Token有效性")
async def verify_token(current_user: dict = Depends(get_current_user)):
    return success_response(
        {
            "is_valid": True,
            "username": current_user["username"],
            "role": current_user.get("role"),
        }
    )
