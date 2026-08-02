"""Forward Uptime Kuma webhooks to a configured QQ group."""

from __future__ import annotations

import json
import secrets
from typing import Any

from nonebot import get_bots, get_driver, get_plugin_config, logger, on_command
from nonebot.adapters.qq import Bot, GroupMessageCreateEvent
from nonebot.drivers import HTTPServerSetup, Request, Response
from nonebot.rule import to_me
from pydantic import BaseModel, Field
from yarl import URL


class Config(BaseModel):
    """Plugin settings loaded from the NoneBot environment."""

    target_group_openid: str = Field(min_length=1)
    uptime_kuma_webhook_token: str = Field(min_length=16)


config = get_plugin_config(Config)


def _json_response(status_code: int, payload: dict[str, str]) -> Response:
    return Response(
        status_code,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content=json.dumps(payload, ensure_ascii=False),
    )


def _webhook_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return request.headers.get("X-Webhook-Token", "")


def _format_webhook_message(payload: Any, raw_body: Any) -> str:
    if isinstance(payload, dict):
        for key in ("msg", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    if isinstance(raw_body, bytes):
        return raw_body.decode("utf-8", errors="replace").strip()
    if isinstance(raw_body, str):
        return raw_body.strip()
    return ""


def _get_qq_bot() -> Bot | None:
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            return bot
    return None


async def handle_uptime_kuma_webhook(request: Request) -> Response:
    """Validate an Uptime Kuma webhook and forward it to the configured group."""
    supplied_token = _webhook_token(request)
    if not secrets.compare_digest(supplied_token, config.uptime_kuma_webhook_token):
        return _json_response(401, {"detail": "invalid webhook token"})

    message = _format_webhook_message(request.json, request.content)
    if not message:
        return _json_response(400, {"detail": "webhook body is empty"})

    qq_bot = _get_qq_bot()
    if qq_bot is None:
        logger.warning("Uptime Kuma webhook received before the QQ bot connected")
        return _json_response(503, {"detail": "QQ bot is not connected"})

    try:
        await qq_bot.send_to_group(
            group_openid=config.target_group_openid,
            message=message[:1900],
        )
    except Exception:
        logger.exception("Failed to forward Uptime Kuma webhook to QQ group")
        return _json_response(502, {"detail": "failed to send QQ group message"})

    return _json_response(200, {"status": "forwarded"})


get_driver().setup_http_server(
    HTTPServerSetup(
        path=URL("/uptime-kuma"),
        method="POST",
        name="uptime-kuma-webhook",
        handle_func=handle_uptime_kuma_webhook,
    )
)

group_info = on_command("群信息", aliases={"group-info"}, rule=to_me(), priority=10)


@group_info.handle()
async def show_group_info(event: GroupMessageCreateEvent) -> None:
    """Show stable QQ OpenAPI identifiers for the current group."""
    await group_info.finish(
        "当前群聊信息：\n"
        f"群 ID：{event.group_id}\n"
        f"群 OpenID：{event.group_openid}\n"
        f"发送者 OpenID：{event.author.id}"
    )


user_id = on_command("我的ID", aliases={"user-id"}, rule=to_me(), priority=10)


@user_id.handle()
async def show_user_id(event: GroupMessageCreateEvent) -> None:
    """Show the caller's QQ OpenAPI user identifier."""
    await user_id.finish(f"你的 OpenID：{event.author.id}")
