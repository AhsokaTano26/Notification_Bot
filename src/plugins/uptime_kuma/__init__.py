"""Forward Uptime Kuma webhooks to a configured QQ group."""

from __future__ import annotations

import json
from typing import Any

from nonebot import get_bots, get_driver, get_plugin_config, logger, on_command
from nonebot.adapters.qq import Bot, GroupMessageCreateEvent, MessageSegment
from nonebot.drivers import HTTPServerSetup, Request, Response
from pydantic import BaseModel, Field
from yarl import URL


class Config(BaseModel):
    """Plugin settings loaded from the NoneBot environment."""

    target_group_openid: str = Field(min_length=1)


config = get_plugin_config(Config)


def _json_response(status_code: int, payload: dict[str, str]) -> Response:
    return Response(
        status_code,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content=json.dumps(payload, ensure_ascii=False),
    )


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


def _uptime_kuma_markdown(message: str) -> str:
    """Format an alert as safe, readable QQ Markdown."""
    content = message[:1800].replace("```", "'''")
    return f"## 🔔 Uptime Kuma 通知\n\n```text\n{content}\n```"


async def _send_markdown_reply(
    bot: Bot,
    event: GroupMessageCreateEvent,
    markdown: str,
    fallback_text: str,
) -> None:
    """Send a rich reply, with text fallback for unsupported QQ clients."""
    try:
        await bot.send(event, MessageSegment.markdown(markdown))
    except Exception:
        logger.warning("QQ Markdown reply failed; sending plain text instead")
        await bot.send(event, fallback_text)


async def handle_uptime_kuma_webhook(request: Request) -> Response:
    """Forward an Uptime Kuma webhook to the configured group."""

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
            message=MessageSegment.markdown(_uptime_kuma_markdown(message)),
        )
    except Exception:
        logger.warning("QQ Markdown notification failed; sending plain text instead")
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

group_info = on_command("群信息", aliases={"group-info"}, priority=10)


@group_info.handle()
async def show_group_info(bot: Bot, event: GroupMessageCreateEvent) -> None:
    """Show stable QQ OpenAPI identifiers for the current group."""
    fallback_text = (
        "当前群聊信息：\n"
        f"群 ID：{event.group_id}\n"
        f"群 OpenID：{event.group_openid}\n"
        f"发送者 OpenID：{event.author.id}"
    )
    await _send_markdown_reply(
        bot,
        event,
        "## 📋 当前群聊信息\n\n"
        "> 将群 OpenID 填入 `TARGET_GROUP_OPENID` 即可接收告警。\n\n"
        f"- **群 ID**：`{event.group_id}`\n"
        f"- **群 OpenID**：`{event.group_openid}`\n"
        f"- **发送者 OpenID**：`{event.author.id}`",
        fallback_text,
    )


user_id = on_command("我的ID", aliases={"user-id"}, priority=10)


@user_id.handle()
async def show_user_id(bot: Bot, event: GroupMessageCreateEvent) -> None:
    """Show the caller's QQ OpenAPI user identifier."""
    await _send_markdown_reply(
        bot,
        event,
        f"## 👤 用户标识\n\n- **你的 OpenID**：`{event.author.id}`",
        f"你的 OpenID：{event.author.id}",
    )
