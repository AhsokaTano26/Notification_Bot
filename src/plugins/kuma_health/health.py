"""Probe live QQ readiness and push the result to Uptime Kuma."""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from time import monotonic
from typing import Literal

import httpx
from nonebot import get_adapter, get_bots, logger, require
from nonebot.adapters.qq import Adapter, Bot

require("src.plugins.runtime_config")
from src.plugins import runtime_config

CHECK_INTERVAL = 60
REQUEST_TIMEOUT = 10.0
_push_request_active: ContextVar[bool] = ContextVar("kuma_push_request", default=False)


def _filter_push_request_log(_record: logging.LogRecord) -> bool:
    """Hide HTTPX's token-bearing URL only in our own Push request context."""
    return not _push_request_active.get()


logging.getLogger("httpx").addFilter(_filter_push_request_log)


async def check_health() -> tuple[Literal["up", "down"], str]:
    """Require every configured QQ bot to have a ready WebSocket and live API."""
    adapter = get_adapter(Adapter)
    if not adapter.qq_config.qq_bots:
        return "down", "No QQ bots configured"

    checked_bots: list[Bot] = []
    for info in adapter.qq_config.qq_bots:
        if not info.use_websocket:
            return "down", f"QQ Bot {info.id}: WebSocket is disabled"
        bot = get_bots().get(info.id)
        if not isinstance(bot, Bot) or not bot.ready:
            return "down", f"QQ Bot {info.id}: WebSocket is not ready"

        await bot.me()
        checked_bots.append(bot)

    for bot in checked_bots:
        if get_bots().get(bot.self_id) is not bot or not bot.ready:
            return "down", f"QQ Bot {bot.self_id}: WebSocket disconnected during check"

    return "up", "QQ WebSocket ready and identity API healthy"


async def report_health(client: httpx.AsyncClient) -> None:
    """Push current health; a failed delivery is retried on the next cycle."""
    push_url = await runtime_config.store.get_setting("KUMA_PUSH_URL")
    if not push_url:
        return

    started = monotonic()
    try:
        status, message = await asyncio.wait_for(check_health(), REQUEST_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 -- failed probes must report down
        status, message = "down", f"QQ health check failed ({type(exc).__name__})"
    ping = f"{(monotonic() - started) * 1000:.1f}"

    try:
        url = httpx.URL(push_url).copy_merge_params(
            {"status": status, "msg": message, "ping": ping}
        )
        token = _push_request_active.set(True)
        try:
            response = await asyncio.wait_for(client.get(url), REQUEST_TIMEOUT)
        finally:
            _push_request_active.reset(token)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("ok") is not True:
            logger.warning("Kuma health push was rejected; retrying next cycle")
    except (asyncio.TimeoutError, httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        # HTTP exceptions contain the token-bearing URL; log only their type.
        logger.warning(f"Kuma health push failed ({type(exc).__name__})")
