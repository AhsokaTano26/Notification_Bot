"""Periodically report the notification bot's actual QQ health to Kuma."""

from __future__ import annotations

from asyncio import CancelledError, Task, create_task, get_running_loop, sleep
from contextlib import suppress

import httpx
from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from .config import Config
from .health import CHECK_INTERVAL, REQUEST_TIMEOUT, config, report_health

__plugin_meta__ = PluginMetadata(
    name="kuma_health",
    description="Report live QQ WebSocket and identity API health to Uptime Kuma",
    usage="Set KUMA_PUSH_URL to an existing Kuma Push monitor URL",
    config=Config,
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
    """Start one background task when this deployment has a Push URL."""
    global _task  # noqa: PLW0603 -- plugin owns its task's lifecycle
    if config.kuma_push_url.strip() and (_task is None or _task.done()):
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
