"""Exercise the authenticated Cloudflare endpoint with an isolated database."""

# ruff: noqa: PLR2004

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import nonebot
import pytest

if TYPE_CHECKING:
    from src.plugins.runtime_config.database import SettingsStore

PAYLOAD = {
    "name": "Origin availability",
    "text": "The origin is unavailable.",
    "data": {"zone_name": "example.com", "new_status": "unhealthy"},
    "ts": 1793188800,
    "alert_type": "health_check_status_notification",
    "alert_event": "ALERT_STATE_EVENT_START",
    "account_id": "account-id",
    "policy_id": "policy-id",
}


class RecordingBot:
    """Capture messages, optionally failing one destination."""

    def __init__(self, fail_group: str = "") -> None:
        self.messages: list[tuple[str, str]] = []
        self.fail_group = fail_group

    async def send_to_group(self, group_openid: str, message: str) -> None:
        if group_openid == self.fail_group:
            error = "QQ delivery failed"
            raise RuntimeError(error)
        self.messages.append((group_openid, message))


async def _post(
    payload: Any, secret: str | None = "manual-secret-one"
) -> httpx.Response:
    from src.plugins import cloudflare_webhook  # noqa: F401

    headers = {"cf-webhook-auth": secret} if secret is not None else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=nonebot.get_asgi()), base_url="http://test"
    ) as client:
        return await client.post("/webhook/cloudflare", json=payload, headers=headers)


async def test_cloudflare_forwards_to_each_matching_key_group(
    settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.plugins import cloudflare_webhook

    bot = RecordingBot()
    monkeypatch.setattr(cloudflare_webhook, "_get_qq_bot", lambda: bot)
    await settings_store.add_cloudflare_key("one", "manual-secret-one", "g1,g2,g1")
    await settings_store.add_cloudflare_key("two", "manual-secret-two", "g3")
    response = await _post(PAYLOAD)
    assert response.status_code == 200
    assert [group for group, _ in bot.messages] == ["g1", "g2"]
    text = bot.messages[0][1]
    assert "Origin availability" in text
    assert "The origin is unavailable." in text
    assert "example.com" in text
    assert "health_check_status_notification" in text
    assert "告警中" in text
    assert "2026-10-28 20:00:00+08:00" in text
    assert "manual-secret" not in text
    assert (await _post(PAYLOAD, "manual-secret-two")).status_code == 200
    assert bot.messages[-1][0] == "g3"
    await settings_store.remove_cloudflare_key("one")
    assert (await _post(PAYLOAD)).status_code == 401


@pytest.mark.parametrize("secret", [None, "", "wrong-secret-value"])
async def test_cloudflare_authentication_precedes_body_validation(
    secret: str | None,
) -> None:
    response = await _post({"not": "a valid notification"}, secret)
    assert response.status_code == 401
    assert "wrong-secret-value" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"text": " "},
        {"text": 42},
        {"text": "alert", "data": []},
        {"text": "alert", "ts": "yesterday"},
        {"text": "alert", "ts": True},
        {"text": "alert", "ts": 99999999999999999999999},
        {"text": "alert", "name": {}},
    ],
)
async def test_cloudflare_rejects_malformed_payload(
    payload: Any, settings_store: SettingsStore
) -> None:
    await settings_store.add_cloudflare_key("one", "manual-secret-one", "g1")
    response = await _post(payload)
    assert response.status_code == 400


async def test_cloudflare_handles_recovery_optional_fields_and_long_details(
    settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.plugins import cloudflare_webhook

    bot = RecordingBot()
    monkeypatch.setattr(cloudflare_webhook, "_get_qq_bot", lambda: bot)
    await settings_store.add_cloudflare_key("one", "manual-secret-one", "g1")
    response = await _post(
        {
            "policy_name": "Recovery",
            "text": "Recovered " + "x" * 10000,
            "data": {"scripts": [{"name": "worker"}]},
            "alert_event": "ALERT_STATE_EVENT_END",
            "future_field": True,
        }
    )
    assert response.status_code == 200
    assert "已恢复" in bot.messages[0][1]
    assert "Recovery" in bot.messages[0][1]
    assert "Recovered" in bot.messages[0][1]
    assert len(bot.messages[0][1]) <= 1900


async def test_cloudflare_reports_disconnected_bot(
    settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.plugins import cloudflare_webhook

    await settings_store.add_cloudflare_key("one", "manual-secret-one", "g1")
    monkeypatch.setattr(cloudflare_webhook, "_get_qq_bot", lambda: None)
    assert (await _post(PAYLOAD)).status_code == 503


async def test_cloudflare_attempts_remaining_groups_after_delivery_failure(
    settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.plugins import cloudflare_webhook

    await settings_store.add_cloudflare_key("one", "manual-secret-one", "g1,g2")
    bot = RecordingBot(fail_group="g1")
    monkeypatch.setattr(cloudflare_webhook, "_get_qq_bot", lambda: bot)
    response = await _post(PAYLOAD)
    assert response.status_code == 502
    assert [group for group, _ in bot.messages] == ["g2"]
