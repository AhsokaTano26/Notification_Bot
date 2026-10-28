"""Periodically report the notification bot's actual QQ health to Kuma."""

from __future__ import annotations

from asyncio import CancelledError, Task, create_task, get_running_loop, sleep
from contextlib import suppress

import httpx
from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from .health import CHECK_INTERVAL, REQUEST_TIMEOUT, report_health

__plugin_meta__ = PluginMetadata(
    name="kuma_health",
    description="Report live QQ WebSocket and identity API health to Uptime Kuma",
    usage="超级管理员通过 /配置 set KUMA_PUSH_URL URL 设置已有的 Kuma Push 监控",
    supported_adapters={"~qq"},
)

driver = get_driver()
_task: Task[None] | None = None


async def _run_health_checks() -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        loop = get_running_loop()
        while True:
            started = loop.time()
            await report_health(client)
            await sleep(max(0, CHECK_INTERVAL - (loop.time() - started)))


@driver.on_startup
async def start_health_task() -> None:
    """Start an idle-capable task so a URL can be configured without restart."""
    global _task  # noqa: PLW0603 -- plugin owns its task's lifecycle
    if _task is None or _task.done():
        _task = create_task(_run_health_checks(), name="kuma_health")


@driver.on_shutdown
async def stop_health_task() -> None:
    """Cancel the health task and wait for its HTTP client to close."""
    global _task  # noqa: PLW0603 -- plugin owns its task's lifecycle
    if _task is not None:
        _task.cancel()
        with suppress(CancelledError):
            await _task
        _task = None
