"""QQ group information and user identifier commands."""

from nonebot import logger, on_command
from nonebot.adapters.qq import (
    Bot,
    C2CMessageCreateEvent,
    GroupMessageCreateEvent,
    MessageSegment,
)
from nonebot.rule import is_type


async def _send_markdown_reply(
    bot: Bot,
    event: GroupMessageCreateEvent,
    markdown: str,
    fallback_text: str,
) -> None:
    """Send a rich reply, with text fallback for unsupported QQ clients."""
    try:
        await bot.send(event, MessageSegment.markdown(markdown))
    except Exception:  # noqa: BLE001 -- QQ API errors use the plain-text fallback
        logger.warning("QQ Markdown reply failed; sending plain text instead")
        await bot.send(event, fallback_text)


group_info = on_command("群信息", aliases={"group-info"}, priority=10)


@group_info.handle()
async def show_group_info(bot: Bot, event: GroupMessageCreateEvent) -> None:
    """Show only the current group identifier."""
    group_id = event.group_openid
    await _send_markdown_reply(
        bot,
        event,
        f"**群ID：**\n```text\n{group_id}\n```",
        group_id,
    )


user_info = on_command(
    "我的ID",
    aliases={"whoami"},
    rule=is_type(GroupMessageCreateEvent, C2CMessageCreateEvent),
    priority=10,
)


@user_info.handle()
async def show_user_info(
    bot: Bot, event: GroupMessageCreateEvent | C2CMessageCreateEvent
) -> None:
    """Expose only the caller's OpenID so the first administrator can bootstrap."""
    await bot.send(event, f"你的 QQ 用户 OpenID：{event.get_user_id()}")
