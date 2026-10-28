"""Toggle ten-second recalls for the commanding user's own group messages."""

from nonebot import get_driver, on_fullmatch
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.qq import Bot, GroupMessageCreateEvent
from nonebot.message import event_preprocessor
from nonebot.plugin import PluginMetadata
from nonebot.rule import is_type

from .recall import RecallManager

__plugin_meta__ = PluginMetadata(
    name="阅后即焚",
    description="开启后自动撤回当前用户在本群发出超过 10 秒的消息",
    usage="发送「阅后即焚」开启自己的阅后即焚，发送「关闭阅后即焚」关闭",
    supported_adapters={"~qq"},
)

driver = get_driver()
manager = RecallManager()
prefixes = {"", *driver.config.command_start}

enable_command = on_fullmatch(
    tuple(f"{prefix}阅后即焚" for prefix in prefixes),
    rule=is_type(GroupMessageCreateEvent),
    priority=10,
    block=True,
)
disable_command = on_fullmatch(
    tuple(f"{prefix}关闭阅后即焚" for prefix in prefixes),
    rule=is_type(GroupMessageCreateEvent),
    priority=10,
    block=True,
)


@enable_command.handle()
async def enable_burn_after_reading(bot: Bot, event: GroupMessageCreateEvent) -> None:
    """Enable recalls for the sender, including this enabling command."""
    if event.author.bot:
        return
    if event.author.member_role != "member":
        await manager.disable(bot.self_id, event.group_openid, event.get_user_id())
        await bot.send(
            event,
            "QQ 官方接口不允许 Bot 撤回群主或管理员的消息，无法为你开启阅后即焚。"
            "此功能仅适用于普通群成员。",
        )
        return
    manager.enable(bot.self_id, event.group_openid, event.get_user_id())
    manager.schedule(bot, event)
    await bot.send(
        event, "已为你开启阅后即焚，你在本群发送的消息将在 10 秒后自动撤回。"
    )


@disable_command.handle()
async def disable_burn_after_reading(bot: Bot, event: GroupMessageCreateEvent) -> None:
    """Cancel only this sender's recalls in the current group."""
    if event.author.bot:
        return
    await manager.disable(bot.self_id, event.group_openid, event.get_user_id())
    await bot.send(event, "已为你关闭阅后即焚，你在本群待执行的自动撤回已取消。")


@event_preprocessor
async def recall_received_group_message(bot: BaseBot, event: BaseEvent) -> None:
    """Observe all received group messages without blocking other matchers."""
    if isinstance(bot, Bot) and isinstance(event, GroupMessageCreateEvent):
        manager.schedule(bot, event)


@driver.on_shutdown
async def stop_recall_tasks() -> None:
    """Release all background recalls when the application stops."""
    await manager.shutdown()
