"""Forward a small, generic JSON notification to one QQ group."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from nonebot import get_bots, get_driver, get_plugin_config, logger
from nonebot.adapters.qq import Bot
from nonebot.drivers import HTTPServerSetup, Request, Response
from pydantic import BaseModel
from yarl import URL

if TYPE_CHECKING:
    from nonebot.drivers.fastapi import Driver as FastAPIDriver

MAX_MESSAGE_LENGTH = 1900
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
ALLOWED_FIELDS = frozenset(
    {"title", "message", "source", "level", "timestamp", "fields", "url"}
)
LEVELS = {
    "info": ("🔵", "通知"),
    "success": ("🟢", "成功"),
    "warning": ("🟡", "警告"),
    "error": ("🔴", "错误"),
}


class Config(BaseModel):
    """Target QQ group OpenID supplied through the environment."""

    general_webhook_group_openid: str = ""


config = get_plugin_config(Config)


def _json_response(status_code: int, detail: dict[str, str]) -> Response:
    return Response(
        status_code,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content=json.dumps(detail, ensure_ascii=False),
    )


def _optional_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError
    return value.strip()


def _timestamp_line(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError
    display = timestamp.astimezone(DISPLAY_TIMEZONE).isoformat(
        sep=" ", timespec="seconds"
    )
    return f"时间：{display}"


def _field_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        raise TypeError
    lines: list[str] = []
    for key, field_value in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError
        if not isinstance(field_value, (str, int, float, bool)):
            raise TypeError
        display = (
            str(field_value).lower()
            if isinstance(field_value, bool)
            else str(field_value)
        )
        lines.append(f"{key.strip()}：{display}")
    return lines


def _validated_url(payload: dict[str, Any]) -> str:
    url = _optional_text(payload, "url")
    if payload.get("url") is not None:
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError
    return url


def _header_line(title: str, level: Any) -> str:
    if level is not None and (not isinstance(level, str) or level not in LEVELS):
        raise ValueError
    if level:
        icon, level_name = LEVELS[level]
        return f"{icon} {title or level_name}"
    return title


def _build_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise TypeError
    if payload.keys() - ALLOWED_FIELDS:
        raise ValueError
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError

    title = _optional_text(payload, "title")
    source = _optional_text(payload, "source")
    url = _validated_url(payload)
    header = _header_line(title, payload.get("level"))
    lines = [header] if header else []

    metadata = [f"来源：{source}"] if source else []
    if timestamp_line := _timestamp_line(payload.get("timestamp")):
        metadata.append(timestamp_line)
    metadata.extend(_field_lines(payload.get("fields")))
    lines.extend(metadata)
    if metadata:
        lines.append("")
    lines.append(message.strip())
    if url:
        lines.append(f"链接：{url}")

    text = "\n".join(lines)
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError
    return text


def _format_message(payload: Any) -> str | None:
    try:
        return _build_message(payload)
    except (TypeError, ValueError):
        return None


def _get_qq_bot() -> Bot | None:
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            return bot
    return None


async def handle_generic_webhook(request: Request) -> Response:
    """Validate a generic notification and send it to the configured group."""
    message = _format_message(request.json)
    if message is None:
        return _json_response(
            400,
            {"detail": "invalid notification JSON or QQ message too long"},
        )

    group_openid = config.general_webhook_group_openid.strip()
    if not group_openid:
        return _json_response(
            503, {"detail": "GENERAL_WEBHOOK_GROUP_OPENID is missing"}
        )

    bot = _get_qq_bot()
    if bot is None:
        logger.warning("Generic webhook received before the QQ bot connected")
        return _json_response(503, {"detail": "QQ bot is not connected"})

    try:
        await bot.send_to_group(group_openid=group_openid, message=message)
    except Exception:  # noqa: BLE001 - QQ adapter and transport errors vary.
        logger.exception("Failed to forward generic webhook to QQ group")
        return _json_response(502, {"detail": "failed to send QQ group message"})

    return _json_response(200, {"status": "forwarded"})


cast("FastAPIDriver", get_driver()).setup_http_server(
    HTTPServerSetup(
        path=URL("/webhook/general"),
        method="POST",
        name="generic-webhook",
        handle_func=handle_generic_webhook,
    )
)
