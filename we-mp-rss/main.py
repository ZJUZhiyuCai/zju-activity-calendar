import argparse
import time

import uvicorn

from core.config import cfg
from core.print import print_info, print_warning
from core.queue import get_queue_runtime_status, start_default_queues


def _should_start_embedded_redis() -> bool:
    return bool(cfg.get("startup.enable_embedded_redis", False)) and bool(
        cfg.get("redis.server.enabled", False)
    )


def _should_start_auth_service() -> bool:
    return bool(cfg.get("startup.enable_auth_service", False))


def parse_runtime_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZJU Activity Calendar runtime")
    parser.add_argument(
        "-config",
        "--config",
        default=cfg.config_path,
        help="运行配置文件路径",
    )
    parser.add_argument(
        "--mode",
        choices=["api", "worker", "auth", "all"],
        default=cfg.get("startup.mode", "api"),
        help="运行模式: api / worker / auth / all",
    )
    return parser.parse_args()


def maybe_start_embedded_redis() -> None:
    if not _should_start_embedded_redis():
        print_info("跳过内置 Redis 启动，使用纯活动 API 模式")
        return

    try:
        from tools.redis_server import run_redis_server

        run_redis_server(config_path=cfg.config_path)
        print_info("已启动内置 Redis 服务")
    except Exception as exc:
        print_warning(f"内置 Redis 启动失败，继续按当前模式运行: {exc}")


def maybe_start_auth_service(*, force: bool = False) -> None:
    if not force and not _should_start_auth_service():
        print_info("跳过公众号授权预热，活动 API 将独立启动")
        return

    try:
        from driver.auth import start_auth_service

        start_auth_service(force_schedule=force)
        print_info("已启动公众号授权服务")
    except Exception as exc:
        print_warning(f"公众号授权服务启动失败，继续按当前模式运行: {exc}")


def start_background_workers() -> None:
    start_default_queues()
    status = get_queue_runtime_status()
    print_info(
        "后台 worker 已启动: "
        f"main={status['main_queue']['is_running']} "
        f"content={status['content_queue']['is_running']}"
    )


def run_api_server() -> None:
    print("启动服务器")
    auto_reload = cfg.get("server.auto_reload", False)
    thread = cfg.get("server.threads", 1)
    reload_dirs = ["apis", "core", "driver", "jobs", "schemas", "tools"]
    uvicorn.run(
        "web:app",
        host="0.0.0.0",
        port=int(cfg.get("port", 8001)),
        reload=auto_reload,
        reload_dirs=reload_dirs,
        reload_excludes=["static", "data", "node_modules", "*.pnpm*"],
        workers=thread,
    )


def run_worker_loop() -> None:
    start_background_workers()
    print_info("worker 模式运行中，按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print_warning("worker 模式已停止")


def run_auth_loop() -> None:
    maybe_start_auth_service(force=True)
    print_info("auth 模式运行中，按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print_warning("auth 模式已停止")


def main() -> None:
    args = parse_runtime_args()
    maybe_start_embedded_redis()

    if args.mode == "api":
        run_api_server()
        return

    if args.mode == "worker":
        run_worker_loop()
        return

    if args.mode == "auth":
        run_auth_loop()
        return

    maybe_start_auth_service(force=True)
    start_background_workers()
    run_api_server()


if __name__ == "__main__":
    main()
