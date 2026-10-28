"""Validate and format Cloudflare's generic notification payload schema."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
MAX_MESSAGE_LENGTH = 1900
EVENT_STATES = {
    "ALERT_STATE_EVENT_START": "🔴 告警中",
    "ALERT_STATE_EVENT_END": "🟢 已恢复",
}


class CloudflarePayload(BaseModel):
    """Allow new Cloudflare fields and alert-specific nested data."""

    model_config = ConfigDict(strict=True, extra="ignore")

    text: str = Field(min_length=1)
    name: str = ""
    policy_name: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    ts: int | None = None
    alert_type: str = ""
    alert_event: str = ""

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        """Whitespace-only descriptions do not form useful notifications."""
        if not value.strip():
            message = "empty notification text"
            raise ValueError(message)
        return value.strip()

    @field_validator("ts")
    @classmethod
    def valid_timestamp(cls, value: int | None) -> int | None:
        """Reject timestamps that cannot be displayed on supported platforms."""
        if value is not None:
            try:
                datetime.fromtimestamp(value, timezone.utc).astimezone(DISPLAY_TIMEZONE)
            except (ValueError, OverflowError, OSError):
                message = "invalid notification timestamp"
                raise ValueError(message) from None
        return value


def format_notification(payload: Any) -> str | None:
    """Return bounded plain text without assuming a particular alert type."""
    try:
        notification = CloudflarePayload.model_validate(payload)
    except ValidationError:
        return None

    title = notification.name.strip() or notification.policy_name.strip() or "通知"
    title = title.replace("\n", " ").replace("\r", " ")[:160]
    status = EVENT_STATES.get(notification.alert_event, "🔵 通知")
    lines = [f"Cloudflare · {status}", f"策略：{title}"]
    if notification.alert_type:
        lines.append(f"类型：{notification.alert_type[:160]}")
    if notification.alert_event and notification.alert_event not in EVENT_STATES:
        lines.append(f"事件：{notification.alert_event[:160]}")
    if notification.ts is not None:
        time = datetime.fromtimestamp(notification.ts, timezone.utc).astimezone(
            DISPLAY_TIMEZONE
        )
        lines.append(f"时间：{time.isoformat(sep=' ', timespec='seconds')}")
    lines.extend(["", notification.text[:1300]])
    if notification.data:
        detail = json.dumps(notification.data, ensure_ascii=False, indent=2)
        lines.extend(["", "详情：", detail[:600]])
    message = "\n".join(lines)
    if len(message) > MAX_MESSAGE_LENGTH:
        return message[: MAX_MESSAGE_LENGTH - 1] + "…"
    return message
