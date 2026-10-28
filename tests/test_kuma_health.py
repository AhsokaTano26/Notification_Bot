"""Exercise QQ health checks and Kuma pushes without live credentials."""

# Literal expectations keep these tests independent of production constants.
# ruff: noqa: PLR2004

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from nonebot.adapters.qq import Adapter, Bot
from nonebot.adapters.qq.config import BotInfo
from nonebot.adapters.qq.config import Config as QQConfig
from nonebot.adapters.qq.event import ReadyEvent
from nonebot.adapters.qq.models import User

from src.plugins import kuma_health
from src.plugins.kuma_health import health

if TYPE_CHECKING:
    from src.plugins.runtime_config.database import SettingsStore

PUSH_URL = "https://kuma.example.com/api/push/test-token"


@pytest.fixture
async def qq_bot(monkeypatch: pytest.MonkeyPatch, settings_store: SettingsStore) -> Bot:
    info = BotInfo(id="test-app", secret="test-secret", use_websocket=True)
    adapter = Mock(spec=Adapter)
    adapter.qq_config = QQConfig.model_validate({"qq_bots": [info]})
    bot = Bot(adapter, info.id, info)
    bot.on_ready(
        ReadyEvent.model_construct(
            version=1,
            session_id="test-session",
            user=User(id="test-user", username="Test Bot", bot=True),
            shard=(0, 1),
        )
    )
    monkeypatch.setattr(bot, "me", AsyncMock(return_value=bot.self_info))
    monkeypatch.setattr(health, "get_adapter", lambda _: adapter)
    monkeypatch.setattr(health, "get_bots", lambda: {bot.self_id: bot})
    await settings_store.set_setting("KUMA_PUSH_URL", PUSH_URL)
    return bot


async def _pushes() -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def receive(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        await health.report_health(client)
    return requests


async def test_pushes_up_only_after_live_identity_check(
    qq_bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = await _pushes()

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.params["status"] == "up"
    assert float(requests[0].url.params["ping"]) >= 0
    # The next probe must call the API again rather than trust cached self_info.
    monkeypatch.setattr(qq_bot, "me", AsyncMock(side_effect=RuntimeError))
    assert (await _pushes())[0].url.params["status"] == "down"


async def test_pushes_down_before_ready(qq_bot: Bot) -> None:
    qq_bot.reset()

    request = (await _pushes())[0]

    assert request.url.params["status"] == "down"
    assert "WebSocket" in request.url.params["msg"]


async def test_pushes_down_for_webhook_mode(qq_bot: Bot) -> None:
    qq_bot.bot_info.use_websocket = False

    assert (await _pushes())[0].url.params["status"] == "down"


@pytest.mark.usefixtures("qq_bot")
async def test_pushes_down_when_bot_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "get_bots", dict)

    assert (await _pushes())[0].url.params["status"] == "down"


async def test_pushes_down_if_another_configured_bot_is_missing(
    qq_bot: Bot,
) -> None:
    qq_bot.adapter.qq_config.qq_bots.append(
        BotInfo(id="missing-app", secret="test-secret")
    )

    assert (await _pushes())[0].url.params["status"] == "down"


async def test_pushes_down_without_configured_bots(qq_bot: Bot) -> None:
    qq_bot.adapter.qq_config.qq_bots.clear()

    assert (await _pushes())[0].url.params["status"] == "down"


@pytest.mark.usefixtures("qq_bot")
async def test_pushes_down_without_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "get_adapter", Mock(side_effect=ValueError))

    assert (await _pushes())[0].url.params["status"] == "down"


async def test_identity_failure_recovers_next_check(
    qq_bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        qq_bot, "me", AsyncMock(side_effect=[RuntimeError, qq_bot.self_info])
    )

    assert (await _pushes())[0].url.params["status"] == "down"
    assert (await _pushes())[0].url.params["status"] == "up"


async def test_identity_timeout_pushes_down(
    qq_bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "REQUEST_TIMEOUT", 0.01)
    monkeypatch.setattr(qq_bot, "me", asyncio.Event().wait)

    request = (await _pushes())[0]

    assert request.url.params["status"] == "down"
    assert "TimeoutError" in request.url.params["msg"]


async def test_disconnect_during_identity_request_pushes_down(
    qq_bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def disconnect() -> User:
        monkeypatch.setattr(health, "get_bots", dict)
        return qq_bot.self_info

    monkeypatch.setattr(qq_bot, "me", disconnect)

    assert (await _pushes())[0].url.params["status"] == "down"


async def test_reset_during_identity_request_pushes_down(
    qq_bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def reset() -> User:
        qq_bot.reset()
        return qq_bot.self_info

    monkeypatch.setattr(qq_bot, "me", reset)

    assert (await _pushes())[0].url.params["status"] == "down"


async def test_replaces_copied_push_parameters_and_preserves_other_query_values(
    qq_bot: Bot, settings_store: SettingsStore
) -> None:
    await settings_store.set_setting(
        "KUMA_PUSH_URL",
        f"{PUSH_URL}?status=up&msg=OK&ping=&extra=keep",
    )
    qq_bot.reset()

    request = (await _pushes())[0]

    assert request.url.path == "/api/push/test-token"
    assert request.url.params.get_list("status") == ["down"]
    assert request.url.params["extra"] == "keep"
    assert request.url.params["msg"] != "OK"


@pytest.mark.usefixtures("qq_bot")
@pytest.mark.parametrize(
    "failure", ["network", "http", "rejected", "json", "payload", "truthy"]
)
async def test_push_failure_does_not_stop_following_checks(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []
    warnings: list[str] = []
    monkeypatch.setattr(health.logger, "warning", warnings.append)

    def receive(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) > 1:
            return httpx.Response(200, json={"ok": True})
        if failure == "network":
            message = f"Connection failed: {PUSH_URL}"
            raise httpx.ConnectError(message, request=request)
        if failure == "http":
            return httpx.Response(503)
        if failure == "json":
            return httpx.Response(200, text="not JSON")
        if failure == "payload":
            return httpx.Response(200, json=[])
        if failure == "truthy":
            return httpx.Response(200, json={"ok": "false"})
        return httpx.Response(200, json={"ok": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        await health.report_health(client)
        await health.report_health(client)

    assert len(requests) == 2
    assert requests[1].url.params["status"] == "up"
    assert len(warnings) == 1
    assert "test-token" not in warnings[0]


async def test_unconfigured_plugin_starts_idle_for_later_configuration() -> None:
    try:
        await kuma_health.start_health_task()
        await asyncio.sleep(0)
        assert kuma_health._task is not None
        assert not kuma_health._task.done()
    finally:
        await kuma_health.stop_health_task()


@pytest.mark.usefixtures("qq_bot")
async def test_database_url_can_enable_change_and_disable_pushes(
    settings_store: SettingsStore,
) -> None:
    await settings_store.set_setting("KUMA_PUSH_URL", "")
    assert await _pushes() == []
    await settings_store.set_setting("KUMA_PUSH_URL", PUSH_URL)
    assert (await _pushes())[0].url.path == "/api/push/test-token"
    await settings_store.set_setting(
        "KUMA_PUSH_URL", "https://other.example/api/push/changed-token"
    )
    assert (await _pushes())[0].url.host == "other.example"
    await settings_store.set_setting("KUMA_PUSH_URL", "")
    assert await _pushes() == []


async def test_background_checks_run_immediately_then_every_sixty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[httpx.AsyncClient] = []
    delays: list[float] = []

    async def report(client: httpx.AsyncClient) -> None:
        clients.append(client)

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(kuma_health, "report_health", report)
    monkeypatch.setattr(kuma_health, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await kuma_health._run_health_checks()

    assert len(clients) == 2
    assert clients[0] is clients[1]
    assert clients[0].is_closed
    assert all(59 <= delay <= 60 for delay in delays)


@pytest.mark.usefixtures("qq_bot")
async def test_startup_is_idempotent_and_shutdown_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    clients: list[httpx.AsyncClient] = []

    async def report(client: httpx.AsyncClient) -> None:
        clients.append(client)
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(kuma_health, "report_health", report)
    try:
        await kuma_health.start_health_task()
        await asyncio.wait_for(started.wait(), timeout=1)
        task = kuma_health._task
        await kuma_health.start_health_task()
        assert kuma_health._task is task
    finally:
        await kuma_health.stop_health_task()

    assert kuma_health._task is None
    assert clients[0].is_closed


async def test_disconnect_of_an_earlier_bot_during_later_probe_pushes_down(
    qq_bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = BotInfo(id="second-app", secret="test-secret")
    qq_bot.adapter.qq_config.qq_bots.append(info)
    second_bot = Bot(qq_bot.adapter, info.id, info)
    second_bot.on_ready(
        ReadyEvent.model_construct(
            version=1,
            session_id="second-session",
            user=User(id="second-user", bot=True),
            shard=(0, 1),
        )
    )
    bots = {qq_bot.self_id: qq_bot, second_bot.self_id: second_bot}
    monkeypatch.setattr(health, "get_bots", lambda: bots)

    async def disconnect_first_bot() -> User:
        bots.pop(qq_bot.self_id)
        return second_bot.self_info

    monkeypatch.setattr(second_bot, "me", disconnect_first_bot)

    assert (await _pushes())[0].url.params["status"] == "down"


@pytest.mark.usefixtures("qq_bot")
async def test_push_timeout_is_bounded_and_next_check_can_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "REQUEST_TIMEOUT", 0.01)
    attempts: list[httpx.Request] = []

    async def receive(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            await asyncio.Event().wait()
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        await health.report_health(client)
        await health.report_health(client)

    assert len(attempts) == 2


@pytest.mark.usefixtures("qq_bot")
@pytest.mark.parametrize("status_code", [200, 503])
async def test_httpx_info_logs_hide_push_token_and_preserve_other_requests(
    caplog: pytest.LogCaptureFixture, status_code: int
) -> None:
    def receive(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"ok": True}, request=request)

    caplog.set_level(logging.INFO, logger="httpx")
    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        await health.report_health(client)
        await client.get("https://unrelated.example.com/health")

    assert "test-token" not in caplog.text
    assert "unrelated.example.com/health" in caplog.text
