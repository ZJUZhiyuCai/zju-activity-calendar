from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

import core.db as db
from apis.base import error_response
from core.config import API_BASE, cfg
from core.models.user import User as DBUser
from core.runtime_bootstrap import get_configured_admin_username


DB = db.Db(tag="用户连接")
SECRET_KEY = cfg.get("secret", "zju-activity-calendar")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(cfg.get("token_expire_minutes", 30))
MAX_LOGIN_ATTEMPTS = 5
USER_CACHE_TTL = 3600
LOGIN_ATTEMPTS_TTL = 1800


class PasswordHasher:
    @staticmethod
    def verify(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False

    @staticmethod
    def hash(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")


pwd_context = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_BASE}/auth/token", auto_error=False)

_user_cache: dict[str, tuple[DBUser, datetime]] = {}
_login_attempts: dict[str, tuple[int, datetime]] = {}


def _cleanup_expired_cache() -> None:
    now = datetime.utcnow()

    expired_users = [
        key
        for key, (_, cached_at) in _user_cache.items()
        if (now - cached_at).total_seconds() > USER_CACHE_TTL
    ]
    for key in expired_users:
        del _user_cache[key]

    expired_attempts = [
        key
        for key, (_, cached_at) in _login_attempts.items()
        if (now - cached_at).total_seconds() > LOGIN_ATTEMPTS_TTL
    ]
    for key in expired_attempts:
        del _login_attempts[key]


def clear_user_cache(username: str | None = None) -> None:
    if username is None:
        _user_cache.clear()
        return

    _user_cache.pop(username, None)


def _clone_user(user: DBUser) -> DBUser:
    data = user.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return DBUser(**data)


def get_user(username: str) -> Optional[DBUser]:
    _cleanup_expired_cache()

    cached = _user_cache.get(username)
    if cached:
        return cached[0]

    session = None
    try:
        session = DB.get_session()
        user = session.query(DBUser).filter(DBUser.username == username).first()
        if not user:
            return None

        cloned = _clone_user(user)
        _user_cache[username] = (cloned, datetime.utcnow())
        return cloned
    except Exception as exc:
        from core.print import print_error

        print_error(f"获取用户错误: {exc}")
        return None
    finally:
        if session is not None:
            session.close()


def get_any_admin_user() -> Optional[DBUser]:
    session = None
    try:
        session = DB.get_session()
        user = session.query(DBUser).filter(DBUser.role == "admin").first()
        if not user:
            return None
        return _clone_user(user)
    except Exception as exc:
        from core.print import print_error

        print_error(f"获取管理员用户错误: {exc}")
        return None
    finally:
        if session is not None:
            session.close()


def get_login_attempts(username: str) -> int:
    _cleanup_expired_cache()
    data = _login_attempts.get(username)
    return data[0] if data else 0


def authenticate_user(username: str, password: str) -> Optional[DBUser]:
    attempts = get_login_attempts(username)
    if attempts >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=error_response(
                code=40101,
                message="用户名或密码错误，您的帐号已锁定，请稍后再试",
            ),
        )

    user = get_user(username)
    if not user or not pwd_context.verify(password, user.password_hash):
        current_attempts = get_login_attempts(username)
        _login_attempts[username] = (current_attempts + 1, datetime.utcnow())
        remaining_attempts = max(MAX_LOGIN_ATTEMPTS - (current_attempts + 1), 0)
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=error_response(
                code=40101,
                message=f"用户名或密码错误，您还有{remaining_attempts}次机会",
            ),
        )

    _login_attempts.pop(username, None)
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = get_user(username)
    if not user:
        raise credentials_exception

    return {
        "username": user.username,
        "role": user.role,
        "permissions": user.permissions,
        "original_user": user,
    }


def _is_local_request(request: Request) -> bool:
    client = request.client
    host = client.host if client else ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


async def get_maintenance_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    if token:
        return await get_current_user(token)

    if cfg.get("maintenance.allow_local_unauthenticated", False) and _is_local_request(request):
        admin_user = get_user(get_configured_admin_username()) or get_any_admin_user()
        return {
            "username": admin_user.username if admin_user else "local-admin",
            "role": admin_user.role if admin_user and admin_user.role else "admin",
            "permissions": admin_user.permissions if admin_user else "all",
            "original_user": admin_user,
            "is_local_bypass": True,
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def requires_role(role: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user or current_user.get("role") != role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator
