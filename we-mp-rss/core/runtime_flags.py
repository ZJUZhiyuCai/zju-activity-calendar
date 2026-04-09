import os

from core.config import cfg


def is_auth_refresh_enabled(*, force: bool = False) -> bool:
    if force:
        return True
    if bool(cfg.get("startup.enable_auth_service", False)):
        return True
    return str(os.getenv("WE_RSS.AUTH", False)) == "True"
