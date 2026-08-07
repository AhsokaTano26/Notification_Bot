"""Forward Alertmanager webhook alerts to a dedicated QQ group."""

from __future__ import annotations

import json
from typing import Any

from nonebot import get_bots, get_driver, get_plugin_config, logger
from nonebot.adapters.qq import Bot, MessageSegment
from nonebot.drivers import HTTPServerSetup, Request, Response
from pydantic import BaseModel
from yarl import URL


class Config(BaseModel):
    """Plugin settings loaded from the NoneBot environment."""

    alertmanager_lanunion_group_openids: str = ""
    alertmanager_tano_group_openids: str = ""


config = get_plugin_config(Config)


def _json_response(status_code: int, payload: dict[str, str]) -> Response:
    return Response(
        status_code,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content=json.dumps(payload, ensure_ascii=False),
    )


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _value(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return str(value).strip() if value is not None and str(value).strip() else None


def _code(value: str) -> str:
    return value.replace("```", "'''").replace("\n", " ")[:300]


def _group_openids(value: str) -> list[str]:
    """Parse a comma-separated environment variable into unique group OpenIDs."""
    openids = (openid.strip() for openid in value.split(","))
    return list(dict.fromkeys(openid for openid in openids if openid))


def _alert_status(status: str | None) -> tuple[str, str]:
    labels = {
        "firing": ("🔴", "告警中"),
        "resolved": ("🟢", "已恢复"),
    }
    return labels.get((status or "").lower(), ("⚪", status or "未知状态"))


def _get_qq_bot() -> Bot | None:
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            return bot
    return None


def _format_alert(
    alert: dict[str, Any],
    common_labels: dict[str, Any],
    common_annotations: dict[str, Any],
    group_status: str | None,
) -> tuple[str, str]:
    """Build compact Markdown and plain-text views for one Alertmanager alert."""
    labels = common_labels | _object(alert.get("labels"))
    annotations = common_annotations | _object(alert.get("annotations"))
    icon, status = _alert_status(_value(alert, "status") or group_status)
    alert_name = _value(labels, "alertname") or "未命名告警"
    title = alert_name.replace("*", "\\*").replace("\n", " ")[:80]

    fields: list[tuple[str, str]] = []
    for label, key in (
        ("等级", "severity"),
        ("实例", "instance"),
        ("任务", "job"),
        ("服务", "service"),
    ):
        if value := _value(labels, key):
            fields.append((label, value))
    if summary := _value(annotations, "summary"):
        fields.append(("摘要", summary))
    if description := _value(annotations, "description"):
        fields.append(("描述", description))
    if starts_at := _value(alert, "startsAt"):
        fields.append(("开始", starts_at))
    if ends_at := _value(alert, "endsAt"):
        if not ends_at.startswith("0001-01-01"):
            fields.append(("结束", ends_at))

    markdown_fields = "\n".join(f"{label}：{_code(value)}" for label, value in fields)
    plain_fields = "\n".join(f"{label}：{value}" for label, value in fields)
    heading = f"**{icon} {title} · {status}**"
    if generator_url := _value(alert, "generatorURL"):
        heading += f"\n\n[查看 Prometheus]({generator_url})"
    markdown = f"{heading}\n\n```text\n{markdown_fields}\n```"
    plain_text = f"{icon} {alert_name} · {status}\n{plain_fields}".strip()
    return markdown, plain_text


async def _send_alert(
    bot: Bot,
    target_group_openid: str,
    markdown: str,
    fallback_text: str,
) -> bool:
    try:
        await bot.send_to_group(
            group_openid=target_group_openid,
            message=MessageSegment.markdown(markdown),
        )
        return True
    except Exception:
        logger.warning("Alertmanager Markdown message failed; sending plain text")
        try:
            await bot.send_to_group(
                group_openid=target_group_openid,
                message=fallback_text[:1900],
            )
            return True
        except Exception:
            logger.exception("Failed to forward Alertmanager alert to QQ group")
            return False


async def _forward_alertmanager_webhook(
    request: Request,
    route_name: str,
    target_group_openids: list[str],
) -> Response:
    """Parse every Alertmanager alert and forward it to all route targets."""
    if not target_group_openids:
        return _json_response(
            503,
            {"detail": f"Alertmanager {route_name} target groups are not configured"},
        )

    payload = _object(request.json)
    alert_values = payload.get("alerts")
    if not isinstance(alert_values, list):
        return _json_response(400, {"detail": "Alertmanager alerts array is missing"})
    alerts = [alert for alert in alert_values if isinstance(alert, dict)]
    if not alerts:
        return _json_response(400, {"detail": "Alertmanager alerts array is empty"})

    qq_bot = _get_qq_bot()
    if qq_bot is None:
        logger.warning("Alertmanager webhook received before the QQ bot connected")
        return _json_response(503, {"detail": "QQ bot is not connected"})

    common_labels = _object(payload.get("commonLabels"))
    common_annotations = _object(payload.get("commonAnnotations"))
    group_status = _value(payload, "status")
    sent = 0
    total = len(alerts) * len(target_group_openids)
    for alert in alerts:
        markdown, fallback_text = _format_alert(
            alert, common_labels, common_annotations, group_status
        )
        for target_group_openid in target_group_openids:
            if await _send_alert(qq_bot, target_group_openid, markdown, fallback_text):
                sent += 1

    if sent != total:
        return _json_response(502, {"detail": f"forwarded {sent}/{total} messages"})
    return _json_response(200, {"status": "forwarded", "messages": str(sent)})


async def handle_lanunion_alertmanager_webhook(request: Request) -> Response:
    """Forward the Lanunion Alertmanager route to its configured QQ groups."""
    return await _forward_alertmanager_webhook(
        request,
        "lanunion",
        _group_openids(config.alertmanager_lanunion_group_openids),
    )


async def handle_tano_alertmanager_webhook(request: Request) -> Response:
    """Forward the Tano Alertmanager route to its configured QQ groups."""
    return await _forward_alertmanager_webhook(
        request,
        "tano",
        _group_openids(config.alertmanager_tano_group_openids),
    )


get_driver().setup_http_server(
    HTTPServerSetup(
        path=URL("/alert/lanunion"),
        method="POST",
        name="alertmanager-lanunion-webhook",
        handle_func=handle_lanunion_alertmanager_webhook,
    )
)
get_driver().setup_http_server(
    HTTPServerSetup(
        path=URL("/alert/tano"),
        method="POST",
        name="alertmanager-tano-webhook",
        handle_func=handle_tano_alertmanager_webhook,
    )
)
