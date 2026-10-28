"""QQ administration commands with database-backed permission checks."""

import shlex

from nonebot import on_command
from nonebot.adapters.qq import (
    Bot,
    C2CMessageCreateEvent,
    GroupMessageCreateEvent,
    Message,
)
from nonebot.params import CommandArg
from nonebot.permission import Permission
from nonebot.rule import is_type

from .database import SETTING_KEYS

HELP_TEXT = """通知 Bot 管理（仅超级管理员）
/配置 help 或 /help 或 /帮助：本帮助
/配置 list：查看配置（Push URL 隐藏）
/配置 set 配置项 值：保存并即时生效
/配置 unset 配置项：清空，停用对应通知
配置项：
TARGET_GROUP_OPENID：/uptime-kuma，单群
TARGET_GROUP_LANUNION_OPENID：/uptime-kuma/lanunion，单群
ALERTMANAGER_LANUNION_GROUP_OPENIDS：/alert/lanunion，多群
ALERTMANAGER_TANO_GROUP_OPENIDS：/alert/tano，多群
GENERAL_WEBHOOK_GROUP_OPENID：/webhook/general，单群
KUMA_PUSH_URL：Kuma Push URL，最迟 60 秒生效
群值可填写「当前群」，或 /群信息 返回的 OpenID；多个群用英文逗号分隔。
/配置 admin list：查看超级管理员
/配置 admin add 用户OpenID：添加超级管理员
/配置 admin remove 用户OpenID：删除，不能删除最后一位
/配置 cloudflare list：查看密钥名称及目标群
/配置 cloudflare add 名称 密钥 群OpenID：手动创建，支持多个群或「当前群」
/配置 cloudflare remove 名称：撤销密钥
Cloudflare URL：/webhook/cloudflare；Secret 填同一密钥。
密钥须为 16-256 个非空格可打印 ASCII 字符，只保存摘要、不回显。
含空格的值使用英文引号；建议私聊填写密钥和 Push URL。
"""
REPLY_LIMIT = 1900
QQMessageEvent = GroupMessageCreateEvent | C2CMessageCreateEvent


def _current_group(value: str, group_openid: str | None) -> str:
    if value != "当前群":
        return value
    if group_openid is None:
        message = "私聊中不能使用「当前群」，请填写群 OpenID"
        raise ValueError(message)
    return group_openid


async def _admin_command(parts: list[str]) -> str:
    from . import store

    match parts:
        case ["list"]:
            return "超级管理员：\n" + "\n".join(await store.list_superusers())
        case ["add", user_id]:
            await store.add_superuser(user_id)
            return "已添加超级管理员。"
        case ["remove", user_id]:
            await store.remove_superuser(user_id)
            return "已删除超级管理员。"
    return HELP_TEXT


async def _cloudflare_command(parts: list[str], group_openid: str | None) -> str:
    from . import store

    match parts:
        case ["list"]:
            keys = await store.list_cloudflare_keys()
            return "Cloudflare 密钥：\n" + (
                "\n".join(
                    f"{name} → {','.join(groups)}" for name, groups in keys.items()
                )
                or "尚未配置"
            )
        case ["add", name, secret, groups]:
            await store.add_cloudflare_key(
                name, secret, _current_group(groups, group_openid)
            )
            return "已创建 Cloudflare 密钥及目标群，密钥不回显。"
        case ["remove", name]:
            await store.remove_cloudflare_key(name)
            return "已撤销 Cloudflare 密钥。"
    return HELP_TEXT


async def _execute_command(parts: list[str], group_openid: str | None) -> str:
    from . import store

    match parts:
        case ["list"]:
            settings = await store.all_settings()
            if settings["KUMA_PUSH_URL"]:
                settings["KUMA_PUSH_URL"] = "已设置（隐藏）"
            return "运行配置：\n" + "\n".join(
                f"{key}={value or '未设置'}" for key, value in settings.items()
            )
        case ["set", key, value]:
            if key.upper() in SETTING_KEYS and key.upper() != "KUMA_PUSH_URL":
                value = _current_group(value, group_openid)
            await store.set_setting(key, value)
            return "已保存配置，无需重启；Kuma 检查最迟 60 秒生效。"
        case ["unset", key]:
            await store.set_setting(key, "")
            return "已清空配置，对应通知已停用。"
        case ["admin", *arguments]:
            return await _admin_command(arguments)
        case ["cloudflare", *arguments]:
            return await _cloudflare_command(arguments, group_openid)
    return HELP_TEXT


async def process_command(
    user_id: str, arguments: str, *, group_openid: str | None = None
) -> str | None:
    """Authorize every invocation and never echo a secret-bearing command."""
    from . import store

    if not await store.is_superuser(user_id):
        return None
    try:
        parts = shlex.split(arguments)
    except ValueError:
        return "参数引号未闭合，请使用 /配置 help 查看格式。"
    try:
        return await _execute_command(parts, group_openid)
    except ValueError as exc:
        return str(exc)


async def is_database_superuser(event: QQMessageEvent) -> bool:
    """Use QQ OpenAPI user identities, independent of QQ group member roles."""
    from . import store

    return await store.is_superuser(event.get_user_id())


manage = on_command(
    "配置",
    aliases={"bot-config"},
    rule=is_type(GroupMessageCreateEvent, C2CMessageCreateEvent),
    permission=Permission(is_database_superuser),
    priority=5,
    block=True,
)
help_command = on_command(
    "help",
    aliases={"帮助"},
    rule=is_type(GroupMessageCreateEvent, C2CMessageCreateEvent),
    permission=Permission(is_database_superuser),
    priority=5,
    block=True,
)


async def _reply(bot: Bot, event: QQMessageEvent, arguments: str) -> None:
    group_openid = (
        event.group_openid if isinstance(event, GroupMessageCreateEvent) else None
    )
    response = await process_command(
        event.get_user_id(), arguments, group_openid=group_openid
    )
    if response:
        for offset in range(0, len(response), REPLY_LIMIT):
            await bot.send(event, response[offset : offset + REPLY_LIMIT])


@manage.handle()
async def manage_settings(
    bot: Bot, event: QQMessageEvent, arguments: Message = CommandArg()
) -> None:
    """Handle configuration in a QQ group or C2C conversation."""
    await _reply(bot, event, arguments.extract_plain_text())


@help_command.handle()
async def show_help(bot: Bot, event: QQMessageEvent) -> None:
    """Show management help only to a current database superuser."""
    await _reply(bot, event, "help")
