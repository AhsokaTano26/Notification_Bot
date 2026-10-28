"""Authenticate Cloudflare notifications and forward to each key's QQ groups."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from nonebot import get_bots, get_driver, logger, require
from nonebot.adapters.qq import Bot
from nonebot.drivers import HTTPServerSetup, Request, Response
from yarl import URL

from .payload import format_notification

if TYPE_CHECKING:
    from nonebot.drivers import ASGIMixin

require("src.plugins.runtime_config")
from src.plugins import runtime_config


def _json_response(status_code: int, payload: dict[str, str]) -> Response:
    return Response(
        status_code,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content=json.dumps(payload, ensure_ascii=False),
    )


def _get_qq_bot() -> Bot | None:
    return next((bot for bot in get_bots().values() if isinstance(bot, Bot)), None)


async def _send_notification(bot: Bot, group_openid: str, message: str) -> bool:
    try:
        await bot.send_to_group(group_openid=group_openid, message=message)
    except Exception as exc:  # noqa: BLE001 -- contain QQ transport/API failures
        logger.warning(
            f"Cloudflare notification delivery failed ({type(exc).__name__})"
        )
        return False
    return True


async def handle_cloudflare_webhook(request: Request) -> Response:
    """Verify cf-webhook-auth before validating or forwarding the JSON body."""
    secret = request.headers.get("cf-webhook-auth", "")
    targets = await runtime_config.store.cloudflare_targets(secret)
    if not targets:
        return _json_response(401, {"detail": "invalid Cloudflare webhook credentials"})

    message = format_notification(request.json)
    if message is None:
        return _json_response(400, {"detail": "invalid Cloudflare notification JSON"})

    bot = _get_qq_bot()
    if bot is None:
        return _json_response(503, {"detail": "QQ bot is not connected"})

    sent = 0
    for group_openid in targets:
        if await _send_notification(bot, group_openid, message):
            sent += 1
    if sent != len(targets):
        return _json_response(
            502, {"detail": f"forwarded {sent}/{len(targets)} messages"}
        )
    return _json_response(200, {"status": "forwarded", "messages": str(sent)})


cast("ASGIMixin", get_driver()).setup_http_server(
    HTTPServerSetup(
        path=URL("/webhook/cloudflare"),
        method="POST",
        name="cloudflare-webhook",
        handle_func=handle_cloudflare_webhook,
    )
)
