"""Existing webhooks must use the live database instead of environment values."""

# ruff: noqa: PLR2004

from typing import Any

import pytest
from nonebot.drivers import Request

from src.plugins import alertmanager_webhook, generic_webhook, uptime_kuma
from src.plugins.runtime_config.database import SettingsStore


class RecordingBot:
    """Capture deliveries without calling QQ."""

    def __init__(self) -> None:
        self.targets: list[str] = []

    async def send_to_group(self, group_openid: str, message: Any) -> None:
        del message
        self.targets.append(group_openid)


@pytest.mark.parametrize(
    "case",
    [
        (
            uptime_kuma,
            "handle_uptime_kuma_webhook",
            "TARGET_GROUP_OPENID",
            {"msg": "up"},
        ),
        (
            uptime_kuma,
            "handle_lanunion_uptime_kuma_webhook",
            "TARGET_GROUP_LANUNION_OPENID",
            {"msg": "up"},
        ),
        (
            generic_webhook,
            "handle_generic_webhook",
            "GENERAL_WEBHOOK_GROUP_OPENID",
            {"message": "up"},
        ),
        (
            alertmanager_webhook,
            "handle_lanunion_alertmanager_webhook",
            "ALERTMANAGER_LANUNION_GROUP_OPENIDS",
            {"alerts": [{"labels": {"alertname": "Test"}}]},
        ),
        (
            alertmanager_webhook,
            "handle_tano_alertmanager_webhook",
            "ALERTMANAGER_TANO_GROUP_OPENIDS",
            {"alerts": [{"labels": {"alertname": "Test"}}]},
        ),
    ],
)
async def test_route_reads_changed_and_cleared_setting(
    case: tuple[Any, str, str, dict[str, Any]],
    settings_store: SettingsStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, handler_name, setting, payload = case
    bot = RecordingBot()
    monkeypatch.setattr(module, "_get_qq_bot", lambda: bot)
    handler = getattr(module, handler_name)
    request = Request("POST", "http://localhost/test", json=payload)
    await settings_store.set_setting(setting, "first")
    assert (await handler(request)).status_code == 200
    await settings_store.set_setting(setting, "second")
    assert (await handler(request)).status_code == 200
    await settings_store.set_setting(setting, "")
    assert (await handler(request)).status_code == 503
    assert bot.targets == ["first", "second"]


async def test_alertmanager_delivers_each_alert_once_per_unique_group(
    settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    bot = RecordingBot()
    monkeypatch.setattr(alertmanager_webhook, "_get_qq_bot", lambda: bot)
    await settings_store.set_setting("ALERTMANAGER_TANO_GROUP_OPENIDS", "g1,g2,g1")
    request = Request("POST", "http://localhost/alert/tano", json={"alerts": [{}, {}]})
    response = await alertmanager_webhook.handle_tano_alertmanager_webhook(request)
    assert response.status_code == 200
    assert bot.targets == ["g1", "g2", "g1", "g2"]
