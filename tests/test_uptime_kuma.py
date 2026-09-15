"""Tests for Uptime Kuma notification formatting and routing."""

from typing import Any

import pytest
from nonebot.drivers import Request

from src.plugins import uptime_kuma
from src.plugins.uptime_kuma import _uptime_kuma_notification

HTTP_OK = 200
WEBHOOK_URL = "http://localhost/uptime-kuma/lanunion"


class FakeBot:
    """Records group messages instead of sending them to QQ."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []

    async def send_to_group(self, group_openid: str, message: Any) -> None:
        self.sent.append((group_openid, message))


def _request() -> Request:
    """Build the same Request shape the FastAPI driver produces."""
    return Request(
        "POST",
        WEBHOOK_URL,
        json={"msg": "Disk usage alert"},
        content=b"",
    )


def test_formats_certificate_expiry_message() -> None:
    markdown, plain_text = _uptime_kuma_notification(
        {
            "msg": (
                "[Tano博客（国内）][https://tano.asia] server certificate "
                "tano.asia will expire in 21 days"
            ),
        },
        b"",
    )

    assert "**🟡 Tano博客（国内） · 证书即将到期**" in markdown
    assert "地址：https://tano.asia" in markdown
    assert "证书域名：tano.asia" in markdown
    assert "剩余时间：21 天" in markdown
    assert "🟡 Tano博客（国内） · 证书即将到期" in plain_text


def test_formats_urgent_certificate_expiry_message() -> None:
    markdown, _ = _uptime_kuma_notification(
        {
            "msg": (
                "[Tano博客（国内）][https://tano.asia] server certificate "
                "tano.asia will expire in 7 days"
            ),
        },
        b"",
    )

    assert "**🔴 Tano博客（国内） · 证书即将到期**" in markdown


async def test_default_route_sends_to_default_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(uptime_kuma, "_get_qq_bot", lambda: bot)

    response = await uptime_kuma.handle_uptime_kuma_webhook(_request())

    assert response.status_code == HTTP_OK
    assert [openid for openid, _ in bot.sent] == ["test-openid"]


async def test_lanunion_route_sends_to_lanunion_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(uptime_kuma, "_get_qq_bot", lambda: bot)

    response = await uptime_kuma.handle_lanunion_uptime_kuma_webhook(_request())

    assert response.status_code == HTTP_OK
    assert [openid for openid, _ in bot.sent] == ["test-lanunion-openid"]
