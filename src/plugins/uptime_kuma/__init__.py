"""Forward Uptime Kuma webhooks to a configured QQ group."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from nonebot import get_bots, get_driver, get_plugin_config, logger
from nonebot.adapters.qq import Bot, MessageSegment
from nonebot.drivers import HTTPServerSetup, Request, Response
from pydantic import BaseModel, Field
from yarl import URL


class Config(BaseModel):
    """Plugin settings loaded from the NoneBot environment."""

    target_group_openid: str = Field(min_length=1)


config = get_plugin_config(Config)
UTC_PLUS_8 = timezone(timedelta(hours=8))


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


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_value(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _code(value: str) -> str:
    """Make a value safe for a single-line Markdown code span."""
    return value.replace("`", "'").replace("\n", " ")[:180]


def _utc_plus_8(value: str) -> str:
    """Convert an ISO 8601 UTC timestamp to UTC+8 for display."""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(UTC_PLUS_8).isoformat(sep=" ", timespec="milliseconds")


def _status(status: Any) -> tuple[str, str]:
    labels = {
        "0": ("🔴", "故障"),
        "1": ("🟢", "正常"),
        "2": ("🟡", "等待中"),
        "3": ("🔵", "维护中"),
    }
    return labels.get(str(status), ("⚪", "未知状态"))


def _uptime_kuma_notification(payload: Any, raw_body: Any) -> tuple[str, str]:
    """Build Markdown and plain-text views of an Uptime Kuma alert."""
    message = _format_webhook_message(payload, raw_body)
    monitor = _object(payload.get("monitor")) if isinstance(payload, dict) else {}
    heartbeat = _object(payload.get("heartbeat")) if isinstance(payload, dict) else {}
    icon, status = _status(heartbeat.get("status"))
    monitor_name = _first_value(monitor, "name")

    fields: list[tuple[str, str]] = []
    if monitor_name:
        fields.append(("监控", monitor_name))
    if monitor_type := _first_value(monitor, "type"):
        fields.append(("类型", monitor_type))
    if url := _first_value(monitor, "url", "hostname"):
        fields.append(("地址", url))
    monitor_id = _first_value(monitor, "id")
    if monitor_id:
        fields.append(("监控 ID", monitor_id))
    if ping := _first_value(heartbeat, "ping"):
        fields.append(("延迟", f"{ping} ms"))
    if time := _first_value(heartbeat, "time"):
        fields.append(("时间", _utc_plus_8(time)))

    markdown_fields = "\n".join(
        f"{label}：{_code(value)}" for label, value in fields
    )
    plain_fields = "\n".join(f"{label}：{value}" for label, value in fields)
    title_name = (monitor_name or "Uptime Kuma").replace("*", "\\*").replace(
        "\n", " "
    )[:80]
    heading = f"**{icon} {title_name} · {status}**"
    dashboard_link = ""
    if monitor_id:
        dashboard_url = (
            "https://status.tano.asia/dashboard/"
            f"{quote(monitor_id, safe='')}"
        )
        dashboard_link = f"[查看监控]({dashboard_url})"
    markdown_prefix = f"{markdown_fields}\n\n" if markdown_fields else ""
    plain_prefix = (
        f"{icon} {monitor_name or 'Uptime Kuma'} · {status}\n{plain_fields}"
    ).strip()

    markdown_header = f"{heading}\n\n{dashboard_link}" if dashboard_link else heading
    message_limit = max(256, 1800 - len(markdown_header) - len(markdown_prefix))
    markdown_message = message[:message_limit].replace("```", "'''")
    markdown = f"{markdown_header}\n\n```text\n{markdown_prefix}{markdown_message}\n```"
    plain_text = f"{plain_prefix}\n\n{message}".strip()
    return markdown, plain_text


async def handle_uptime_kuma_webhook(request: Request) -> Response:
    """Forward an Uptime Kuma webhook to the configured group."""

    markdown, message = _uptime_kuma_notification(request.json, request.content)
    if not message:
        return _json_response(400, {"detail": "webhook body is empty"})

    qq_bot = _get_qq_bot()
    if qq_bot is None:
        logger.warning("Uptime Kuma webhook received before the QQ bot connected")
        return _json_response(503, {"detail": "QQ bot is not connected"})

    try:
        await qq_bot.send_to_group(
            group_openid=config.target_group_openid,
            message=MessageSegment.markdown(markdown),
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
