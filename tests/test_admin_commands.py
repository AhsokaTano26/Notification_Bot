"""Dispatch real QQ events to check admin matchers and bootstrap identity lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import nonebot
import pytest
from nonebot.adapters.qq import Bot, C2CMessageCreateEvent, GroupMessageCreateEvent
from nonebot.adapters.qq.config import BotInfo
from nonebot.message import handle_event

if TYPE_CHECKING:
    from nonebot.adapters.qq import Adapter

from src.plugins import group_tools  # noqa: F401 -- register the public ID helper


class RecordingAdapter:
    """Retain NoneBot dispatch, replacing only the external QQ API call."""

    def __init__(self) -> None:
        self.config = nonebot.get_driver().config
        self.messages: list[str] = []

    @classmethod
    def get_name(cls) -> str:
        return "QQ"

    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        del bot, api
        self.messages.append(data.get("content") or str(data.get("markdown", "")))
        return None


def _event(
    content: str, user_id: str, *, private: bool
) -> GroupMessageCreateEvent | C2CMessageCreateEvent:
    payload = {
        "id": "incoming-message",
        "content": content,
        "timestamp": "2026-10-28T12:00:00+00:00",
        "author": {
            "id": "internal-id",
            "bot": False,
            "member_openid": user_id,
            "user_openid": user_id,
            "member_role": "admin",
        },
        "group_id": "internal-group",
        "group_openid": "public-group",
    }
    if private:
        return C2CMessageCreateEvent.model_validate(payload)
    return GroupMessageCreateEvent.model_validate(payload)


@pytest.mark.parametrize("private", [False, True])
async def test_help_permission_and_configuration_dispatch(*, private: bool) -> None:
    from src.plugins.runtime_config import store

    adapter = RecordingAdapter()
    bot = Bot(
        cast("Adapter", adapter),
        "test-app",
        BotInfo(id="test-app", secret="test-secret"),
    )
    await handle_event(bot, _event("/help", "ordinary-user", private=private))
    await handle_event(
        bot,
        _event(
            "/配置 set TARGET_GROUP_OPENID attacker", "ordinary-user", private=private
        ),
    )
    assert adapter.messages == []
    assert await store.get_setting("TARGET_GROUP_OPENID") == "test-openid"
    await handle_event(bot, _event("/help", "test-admin", private=private))
    assert any("KUMA_PUSH_URL" in message for message in adapter.messages)
    await handle_event(
        bot,
        _event("/配置 set TARGET_GROUP_OPENID updated", "test-admin", private=private),
    )
    assert await store.get_setting("TARGET_GROUP_OPENID") == "updated"


@pytest.mark.parametrize("private", [False, True])
async def test_user_can_obtain_identity_before_admin_bootstrap(
    *, private: bool
) -> None:
    adapter = RecordingAdapter()
    bot = Bot(
        cast("Adapter", adapter),
        "test-app",
        BotInfo(id="test-app", secret="test-secret"),
    )
    await handle_event(bot, _event("/我的ID", "ordinary-user", private=private))
    assert any("ordinary-user" in message for message in adapter.messages)


async def test_group_lookup_returns_the_group_openid_used_by_webhooks() -> None:
    adapter = RecordingAdapter()
    bot = Bot(
        cast("Adapter", adapter),
        "test-app",
        BotInfo(id="test-app", secret="test-secret"),
    )
    await handle_event(bot, _event("/群信息", "ordinary-user", private=False))
    assert any("public-group" in message for message in adapter.messages)
    assert all("internal-group" not in message for message in adapter.messages)


@pytest.mark.parametrize("separator", ["", " ", "\t", "\n"])
@pytest.mark.parametrize("command", ["配置", "bot-config"])
async def test_secret_command_event_logs_are_hidden(
    separator: str, command: str
) -> None:
    from nonebot import logger

    from src.plugins.runtime_config import store

    adapter = RecordingAdapter()
    bot = Bot(
        cast("Adapter", adapter),
        "test-app",
        BotInfo(id="test-app", secret="test-secret"),
    )
    messages: list[str] = []
    handler = logger.add(
        lambda message: messages.append(str(message)), format="{message}"
    )
    try:
        await handle_event(
            bot,
            _event(
                f"/{command}{separator}cloudflare add example private-secret-value g1",
                "test-admin",
                private=True,
            ),
        )
    finally:
        logger.remove(handler)
    assert await store.cloudflare_targets("private-secret-value") == ["g1"]
    assert "private-secret-value" not in "\n".join(messages)
