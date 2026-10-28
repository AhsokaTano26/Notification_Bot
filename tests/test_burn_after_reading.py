"""Exercise personal message recalls without connecting to QQ."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, cast

import nonebot
import pytest
import pytest_asyncio
from nonebot.adapters.qq import Bot, C2CMessageCreateEvent, GroupMessageCreateEvent
from nonebot.adapters.qq.config import BotInfo
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.adapters.qq.models import PostGroupMessagesReturn
from nonebot.drivers import Response
from nonebot.message import handle_event

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from nonebot.adapters.qq import Adapter

    from src.plugins.burn_after_reading.recall import RecallManager


class FakeQQAdapter:
    """Capture external QQ calls while retaining real event dispatch."""

    def __init__(self) -> None:
        self.config = nonebot.get_driver().config
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_recall = False
        self.recall_error: Exception | None = None

    @classmethod
    def get_name(cls) -> str:
        return "QQ"

    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        del bot
        self.calls.append((api, data))
        if api == "post_group_messages":
            return PostGroupMessagesReturn(id="bot-reply")
        if api == "delete_group_message" and self.fail_recall:
            raise RuntimeError
        if api == "delete_group_message" and self.recall_error is not None:
            raise self.recall_error
        return None


def make_bot(adapter: FakeQQAdapter, bot_id: str = "test-bot") -> Bot:
    return Bot(
        cast("Adapter", adapter), bot_id, BotInfo(id=bot_id, secret="test-secret")
    )


def group_event(
    content: str = "personal message",
    *,
    user_id: str = "user-a",
    group_id: str = "group-a",
    message_id: str = "user-message",
) -> GroupMessageCreateEvent:
    return GroupMessageCreateEvent.model_validate(
        {
            "id": message_id,
            "content": content,
            "timestamp": "2023-11-14T22:13:20+00:00",
            "group_id": "internal-group-id",
            "group_openid": group_id,
            "author": {
                "id": "internal-user-id",
                "bot": False,
                "member_openid": user_id,
                "member_role": "member",
            },
        }
    )


class ControlledDelay:
    """Hold timers until their requested delay has been inspected."""

    def __init__(self) -> None:
        self.seconds: list[float] = []
        self.release = asyncio.Event()

    async def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)
        await self.release.wait()


@pytest_asyncio.fixture
async def recall_manager() -> AsyncIterator[RecallManager]:
    from src.plugins.burn_after_reading.recall import RecallManager

    manager = RecallManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


@pytest.fixture
def delay(monkeypatch: pytest.MonkeyPatch) -> ControlledDelay:
    from src.plugins.burn_after_reading import recall

    controlled = ControlledDelay()
    monkeypatch.setattr(recall, "sleep", controlled)
    monkeypatch.setattr(recall, "time", lambda: 1_700_000_000, raising=False)
    return controlled


@pytest.fixture
def plugin(recall_manager: RecallManager, monkeypatch: pytest.MonkeyPatch) -> Any:
    from src.plugins import burn_after_reading

    monkeypatch.setattr(burn_after_reading, "manager", recall_manager)
    return burn_after_reading


async def test_recall_waits_ten_seconds_for_enabled_users_message(
    recall_manager: RecallManager, delay: ControlledDelay
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    recall_manager.schedule(bot, group_event())
    await asyncio.sleep(0)

    assert delay.seconds == [10]
    assert adapter.calls == []
    delay.release.set()
    await asyncio.sleep(0)

    assert adapter.calls == [
        (
            "delete_group_message",
            {"group_openid": "group-a", "message_id": "user-message"},
        )
    ]


async def test_scope_isolated_by_user_group_and_bot(
    recall_manager: RecallManager, delay: ControlledDelay
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    recall_manager.schedule(bot, group_event(message_id="before-enable"))
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    recall_manager.schedule(bot, group_event(user_id="user-b"))
    recall_manager.schedule(bot, group_event(group_id="group-b"))
    recall_manager.schedule(make_bot(adapter, "other-bot"), group_event())
    delay.release.set()
    await asyncio.sleep(0)

    assert delay.seconds == []
    assert adapter.calls == []


@pytest.mark.parametrize(
    ("timestamp", "remaining"),
    [
        ("2023-11-14T22:13:16+00:00", 6),
        ("2023-11-14T22:13:00+00:00", 0),
        ("2023-11-14T22:13:30+00:00", 10),
        ("invalid", 10),
        ("2023-11-14T22:13:20", 10),
    ],
)
async def test_timer_uses_send_time_with_safe_timestamp_fallback(
    recall_manager: RecallManager,
    delay: ControlledDelay,
    timestamp: str,
    remaining: float,
) -> None:
    bot = make_bot(FakeQQAdapter())
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    event = group_event()
    event.timestamp = timestamp
    recall_manager.schedule(bot, event)
    await asyncio.sleep(0)

    assert delay.seconds == [remaining]


async def test_duplicate_events_schedule_only_one_recall(
    recall_manager: RecallManager, delay: ControlledDelay
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    recall_manager.schedule(bot, group_event())
    recall_manager.schedule(bot, group_event())
    delay.release.set()
    await asyncio.sleep(0)

    assert len(adapter.calls) == 1


async def test_recall_failure_is_contained(
    recall_manager: RecallManager,
    delay: ControlledDelay,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.burn_after_reading import recall

    warnings: list[str] = []
    monkeypatch.setattr(recall.logger, "warning", warnings.append)
    adapter = FakeQQAdapter()
    adapter.fail_recall = True
    bot = make_bot(adapter)
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    recall_manager.schedule(bot, group_event())
    delay.release.set()
    await asyncio.sleep(0)

    assert len(warnings) == 1


async def test_shutdown_cancels_recalls_and_resets_personal_switches(
    recall_manager: RecallManager, delay: ControlledDelay
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    recall_manager.schedule(bot, group_event())
    await asyncio.sleep(0)
    await recall_manager.shutdown()
    recall_manager.schedule(bot, group_event(message_id="after-shutdown"))
    delay.release.set()
    await asyncio.sleep(0)

    assert delay.seconds == [10]
    assert adapter.calls == []


@pytest.mark.parametrize("prefix", ["", "/"])
@pytest.mark.usefixtures("plugin")
async def test_commands_enable_only_the_sender_and_preserve_bot_messages(
    delay: ControlledDelay, prefix: str
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    await handle_event(bot, group_event(f"{prefix}阅后即焚", message_id="enable"))
    await handle_event(bot, group_event(message_id="own-message"))
    await handle_event(bot, group_event(user_id="user-b", message_id="other-user"))
    await bot.send_to_group(group_openid="group-a", message="notification")
    assert delay.seconds == [10, 10]
    delay.release.set()
    await asyncio.sleep(0)

    assert sorted(
        data["message_id"]
        for api, data in adapter.calls
        if api == "delete_group_message"
    ) == ["enable", "own-message"]


async def test_other_users_cannot_disable_the_senders_mode(
    plugin: Any, delay: ControlledDelay
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    plugin.manager.enable(bot.self_id, "group-a", "user-a")
    await handle_event(bot, group_event("关闭阅后即焚", user_id="user-b"))
    await handle_event(bot, group_event(message_id="user-a-message"))
    delay.release.set()
    await asyncio.sleep(0)

    assert [
        data["message_id"]
        for api, data in adapter.calls
        if api == "delete_group_message"
    ] == ["user-a-message"]


@pytest.mark.parametrize("prefix", ["", "/"])
async def test_disable_cancels_only_its_senders_recalls_even_after_reenabling(
    plugin: Any, delay: ControlledDelay, prefix: str
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    plugin.manager.enable(bot.self_id, "group-a", "user-a")
    plugin.manager.enable(bot.self_id, "group-a", "user-b")
    await handle_event(bot, group_event(message_id="cancelled"))
    await handle_event(bot, group_event(user_id="user-b", message_id="kept"))
    await handle_event(bot, group_event(f"{prefix}关闭阅后即焚", message_id="disable"))
    await handle_event(bot, group_event(message_id="after-disable"))
    await handle_event(bot, group_event(f"{prefix}阅后即焚", message_id="reenable"))
    delay.release.set()
    await asyncio.sleep(0)

    assert sorted(
        data["message_id"]
        for api, data in adapter.calls
        if api == "delete_group_message"
    ) == ["kept", "reenable"]


async def test_private_messages_and_bot_events_are_ignored(
    plugin: Any, delay: ControlledDelay
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    plugin.manager.enable(bot.self_id, "group-a", "user-a")
    bot_event = group_event()
    bot_event.author.bot = True
    await handle_event(bot, bot_event)
    private_event = C2CMessageCreateEvent.model_validate(
        {
            "id": "private-message",
            "content": "阅后即焚",
            "timestamp": "2023-11-14T22:13:20+00:00",
            "author": {"id": "user-a", "user_openid": "user-a"},
        }
    )
    await handle_event(bot, private_event)
    delay.release.set()
    await asyncio.sleep(0)

    assert delay.seconds == []
    assert adapter.calls == []


@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.usefixtures("plugin")
async def test_privileged_users_receive_a_limit_notice_instead_of_being_enabled(
    delay: ControlledDelay, role: str
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    enable_event = group_event("阅后即焚", message_id="enable")
    enable_event.author = enable_event.author.model_copy(update={"member_role": role})
    await handle_event(bot, enable_event)
    await handle_event(bot, group_event(message_id="next-message"))
    delay.release.set()
    await asyncio.sleep(0)

    assert delay.seconds == []
    assert len(adapter.calls) == 1
    assert adapter.calls[0][0] == "post_group_messages"
    assert "无法" in adapter.calls[0][1]["content"]
    assert "群主" in adapter.calls[0][1]["content"]


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_promoted_users_messages_are_not_scheduled(
    recall_manager: RecallManager, delay: ControlledDelay, role: str
) -> None:
    adapter = FakeQQAdapter()
    bot = make_bot(adapter)
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    event = group_event()
    event.author = event.author.model_copy(update={"member_role": role})
    recall_manager.schedule(bot, event)
    delay.release.set()
    await asyncio.sleep(0)

    assert delay.seconds == []
    assert adapter.calls == []


async def test_qq_failure_logs_error_code_message_status_and_trace_without_raw_data(
    recall_manager: RecallManager,
    delay: ControlledDelay,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.burn_after_reading import recall

    warnings: list[str] = []
    monkeypatch.setattr(recall.logger, "warning", warnings.append)
    adapter = FakeQQAdapter()
    adapter.recall_error = ActionFailed(
        Response(
            400,
            headers={"X-Tps-trace-ID": "test-trace-id", "Authorization": "secret"},
            content=json.dumps(
                {
                    "code": 40062003,
                    "message": "no permission",
                    "data": {"access_token": "secret"},
                }
            ),
        )
    )
    bot = make_bot(adapter)
    recall_manager.enable(bot.self_id, "group-a", "user-a")
    recall_manager.schedule(bot, group_event())
    delay.release.set()
    await asyncio.sleep(0)

    assert len(warnings) == 1
    assert "400" in warnings[0]
    assert "40062003" in warnings[0]
    assert "no permission" in warnings[0]
    assert "test-trace-id" in warnings[0]
    assert "secret" not in warnings[0]
