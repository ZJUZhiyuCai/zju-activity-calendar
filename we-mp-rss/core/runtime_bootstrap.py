from __future__ import annotations

import os
from datetime import datetime
from typing import Mapping, Optional

from core.app_logging import log_event
from core.models.user import User as DBUser
from core.print import print_info, print_warning


def _get_env(env: Optional[Mapping[str, str]] = None) -> Mapping[str, str]:
    return env if env is not None else os.environ


def _parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_configured_admin_username(env: Optional[Mapping[str, str]] = None) -> str:
    runtime_env = _get_env(env)
    username = str(runtime_env.get("ADMIN_USERNAME", "")).strip()
    return username or "admin"


def get_admin_bootstrap_summary(env: Optional[Mapping[str, str]] = None) -> dict:
    runtime_env = _get_env(env)
    username = get_configured_admin_username(runtime_env)
    password = str(runtime_env.get("ADMIN_PASSWORD", "")).strip()
    password_hash = str(runtime_env.get("ADMIN_PASSWORD_HASH", "")).strip()
    force_update = _parse_bool(runtime_env.get("ADMIN_FORCE_UPDATE_PASSWORD"), default=False)

    configured = bool(password or password_hash)
    credential_source = None
    if password_hash:
        credential_source = "password_hash"
    elif password:
        credential_source = "password"

    return {
        "username": username,
        "configured": configured,
        "force_update": force_update,
        "credential_source": credential_source,
    }


def ensure_admin_user(db_instance=None, env: Optional[Mapping[str, str]] = None) -> dict:
    runtime_env = _get_env(env)
    summary = get_admin_bootstrap_summary(runtime_env)

    if not summary["configured"]:
        print_info("未配置管理员初始化，跳过管理员 bootstrap")
        return {**summary, "status": "disabled"}

    from core.auth import PasswordHasher, clear_user_cache

    password = str(runtime_env.get("ADMIN_PASSWORD", "")).strip()
    password_hash = str(runtime_env.get("ADMIN_PASSWORD_HASH", "")).strip()
    nickname = str(runtime_env.get("ADMIN_NICKNAME", "")).strip() or "Administrator"
    now = datetime.utcnow()
    resolved_password_hash = password_hash or PasswordHasher.hash(password)

    if db_instance is None:
        from core.db import DB as runtime_db

        db_instance = runtime_db

    session = None
    try:
        session = db_instance.get_session()
        user = session.query(DBUser).filter(DBUser.username == summary["username"]).first()
        if user is None:
            session.add(
                DBUser(
                    id=f"user-{summary['username']}",
                    username=summary["username"],
                    password_hash=resolved_password_hash,
                    is_active=True,
                    role="admin",
                    permissions="all",
                    nickname=nickname,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
            clear_user_cache(summary["username"])
            print_info(f"已创建管理员账号: {summary['username']}")
            log_event("info", "admin user bootstrapped", username=summary["username"], action="created")
            return {**summary, "status": "created"}

        changed = False
        if summary["force_update"] and user.password_hash != resolved_password_hash:
            user.password_hash = resolved_password_hash
            changed = True
        if user.role != "admin":
            user.role = "admin"
            changed = True
        if user.permissions != "all":
            user.permissions = "all"
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if nickname and user.nickname != nickname:
            user.nickname = nickname
            changed = True

        if changed:
            user.updated_at = now
            session.commit()
            clear_user_cache(summary["username"])
            action = "updated" if summary["force_update"] else "reconciled"
            print_info(f"已更新管理员账号: {summary['username']}")
            log_event("info", "admin user bootstrapped", username=summary["username"], action=action)
            return {**summary, "status": action}

        print_info(f"管理员账号已就绪: {summary['username']}")
        return {**summary, "status": "unchanged"}
    except Exception as exc:
        if session is not None:
            session.rollback()
        print_warning(f"管理员 bootstrap 失败: {exc}")
        log_event("error", "admin bootstrap failed", username=summary["username"], error=exc)
        return {**summary, "status": "failed", "error": str(exc)}
    finally:
        if session is not None:
            session.close()
