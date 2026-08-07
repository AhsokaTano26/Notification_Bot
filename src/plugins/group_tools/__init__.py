"""QQ group information and user identifier commands."""

from nonebot import logger, on_command
from nonebot.adapters.qq import Bot, GroupMessageCreateEvent, MessageSegment


async def _send_markdown_reply(
    bot: Bot,
    event: GroupMessageCreateEvent,
    markdown: str,
    fallback_text: str,
) -> None:
    """Send a rich reply, with text fallback for unsupported QQ clients."""
    try:
        await bot.send(event, MessageSegment.markdown(markdown))
    except Exception:
        logger.warning("QQ Markdown reply failed; sending plain text instead")
        await bot.send(event, fallback_text)


group_info = on_command("群信息", aliases={"group-info"}, priority=10)


@group_info.handle()
async def show_group_info(bot: Bot, event: GroupMessageCreateEvent) -> None:
    """Show only the current group identifier."""
    group_id = event.group_id
    await _send_markdown_reply(
        bot,
        event,
        "**群ID：**"
        f"```text\n{group_id}\n```",
        group_id,
    )
