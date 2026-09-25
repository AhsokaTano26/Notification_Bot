"""Tests for the generic JSON-to-QQ webhook."""

from typing import TYPE_CHECKING, Any, cast

import httpx
import nonebot
import pytest

from src.plugins import generic_webhook

if TYPE_CHECKING:
    from nonebot.drivers.fastapi import Driver as FastAPIDriver

WEBHOOK_PATH = "/webhook/general"
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_BAD_GATEWAY = 502
HTTP_SERVICE_UNAVAILABLE = 503


class FakeBot:
    """Capture the QQ API boundary without a live QQ connection."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[str, Any]] = []
        self.fail = fail

    async def send_to_group(self, group_openid: str, message: Any) -> None:
        if self.fail:
            raise RuntimeError
        self.sent.append((group_openid, message))


async def _post(payload: Any) -> httpx.Response:
    transport = httpx.ASGITransport(
        app=cast("FastAPIDriver", nonebot.get_driver()).server_app
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        return await client.post(WEBHOOK_PATH, json=payload)


async def test_general_webhook_sends_titled_message_to_configured_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post({"title": "Build", "message": "Deployment finished"})

    assert response.status_code == HTTP_OK
    assert response.json() == {"status": "forwarded"}
    assert bot.sent == [("test-generic-openid", "Build\nDeployment finished")]


async def test_general_webhook_accepts_message_without_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post({"message": "  Deployment finished  "})

    assert response.status_code == HTTP_OK
    assert bot.sent == [("test-generic-openid", "Deployment finished")]


async def test_general_webhook_formats_structured_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post(
        {
            "title": "部署失败",
            "message": "构建失败",
            "source": "CI/CD",
            "level": "error",
            "timestamp": "2026-09-26T12:00:00Z",
            "fields": {"环境": "production", "重试次数": 0, "需回滚": True},
            "url": "https://example.com/build/42",
        }
    )

    assert response.status_code == HTTP_OK
    assert bot.sent == [
        (
            "test-generic-openid",
            "🔴 部署失败\n"
            "来源：CI/CD\n"
            "时间：2026-09-26 20:00:00+08:00\n"
            "环境：production\n"
            "重试次数：0\n"
            "需回滚：true\n"
            "\n构建失败\n"
            "链接：https://example.com/build/42",
        )
    ]


async def test_general_webhook_formats_level_without_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post({"message": "容量接近上限", "level": "warning"})

    assert response.status_code == HTTP_OK
    assert bot.sent == [("test-generic-openid", "🟡 警告\n容量接近上限")]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": "   "},
        {"message": 42},
        {"message": "body", "title": ["bad"]},
        {"message": "body", "source": 42},
        {"message": "body", "level": "critical"},
        {"message": "body", "timestamp": "2026-09-26T12:00:00"},
        {"message": "body", "fields": {"details": {"nested": True}}},
        {"message": "body", "url": "file:///tmp/report"},
        {"message": "body", "unexpected": "silently lost"},
        ["body"],
    ],
)
async def test_general_webhook_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post(payload)

    assert response.status_code == HTTP_BAD_REQUEST
    assert bot.sent == []


async def test_general_webhook_rejects_oversized_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post({"message": "x" * 1901})

    assert response.status_code == HTTP_BAD_REQUEST
    assert bot.sent == []


async def test_general_webhook_rejects_oversized_combined_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)

    response = await _post({"message": "x" * 1890, "fields": {"环境": "production"}})

    assert response.status_code == HTTP_BAD_REQUEST
    assert bot.sent == []


async def test_general_webhook_reports_missing_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: bot)
    monkeypatch.setattr(generic_webhook.config, "general_webhook_group_openid", "")

    response = await _post({"message": "hello"})

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    assert bot.sent == []


async def test_general_webhook_reports_disconnected_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: None)

    response = await _post({"message": "hello"})

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE


async def test_general_webhook_reports_qq_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generic_webhook, "_get_qq_bot", lambda: FakeBot(fail=True))

    response = await _post({"message": "hello"})

    assert response.status_code == HTTP_BAD_GATEWAY
