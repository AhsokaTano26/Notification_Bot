"""Manage personal, cancellable timers for received QQ group messages."""

from __future__ import annotations

from asyncio import Task, create_task, gather, sleep
from datetime import datetime
from time import time
from typing import TYPE_CHECKING

from nonebot import logger

if TYPE_CHECKING:
    from nonebot.adapters.qq import Bot, GroupMessageCreateEvent

RECALL_DELAY = 10
Scope = tuple[str, str, str]


def _remaining_delay(timestamp: str) -> float:
    try:
        sent_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return RECALL_DELAY
    if sent_at.tzinfo is None:
        return RECALL_DELAY
    age = max(0, time() - sent_at.timestamp())
    return max(0, RECALL_DELAY - age)


class RecallManager:
    """Keep mode switches and pending recalls separate for each group member."""

    def __init__(self) -> None:
        self._enabled: set[Scope] = set()
        self._tasks: dict[Scope, dict[str, Task[None]]] = {}

    def enable(self, bot_id: str, group_id: str, user_id: str) -> None:
        """Enable recalls for this user's messages in this group."""
        self._enabled.add((bot_id, group_id, user_id))

    async def disable(self, bot_id: str, group_id: str, user_id: str) -> None:
        """Disable only this user and cancel their outstanding timers."""
        scope = (bot_id, group_id, user_id)
        self._enabled.discard(scope)
        await self._cancel(set(self._tasks.pop(scope, {}).values()))

    def schedule(self, bot: Bot, event: GroupMessageCreateEvent) -> None:
        """Recall an opted-in user's message ten seconds after it was sent."""
        scope = (bot.self_id, event.group_openid, event.get_user_id())
        if scope not in self._enabled or event.author.bot or not event.id:
            return
        tasks = self._tasks.setdefault(scope, {})
        if event.id in tasks:
            return
        task = create_task(
            self._recall(
                bot, event.group_openid, event.id, _remaining_delay(event.timestamp)
            )
        )
        tasks[event.id] = task
        task.add_done_callback(lambda _: tasks.pop(event.id, None))

    async def shutdown(self) -> None:
        """Cancel all timers and reset mode switches at process shutdown."""
        self._enabled.clear()
        tasks = {task for pending in self._tasks.values() for task in pending.values()}
        self._tasks.clear()
        await self._cancel(tasks)

    @staticmethod
    async def _cancel(tasks: set[Task[None]]) -> None:
        for task in tasks:
            task.cancel()
        if tasks:
            await gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _recall(bot: Bot, group_id: str, message_id: str, delay: float) -> None:
        try:
            await sleep(delay)
            await bot.delete_group_message(group_openid=group_id, message_id=message_id)
        except Exception as exc:  # noqa: BLE001 -- contain background QQ API failures
            logger.warning(
                f"Failed to recall QQ group message {message_id} in {group_id}: "
                f"{type(exc).__name__}"
            )
