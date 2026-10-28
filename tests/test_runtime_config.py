"""Persistent configuration and authorization without QQ credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


async def test_database_survives_restart_and_bootstrap_is_not_reapplied(
    tmp_path: Path,
) -> None:
    from src.plugins.runtime_config.database import SettingsStore

    path = tmp_path / "data" / "bot.sqlite3"
    first = SettingsStore(path)
    await first.initialize({"qq:first"})
    await first.set_setting("TARGET_GROUP_OPENID", "group-one")
    await first.add_superuser("second")
    await first.remove_superuser("first")

    restarted = SettingsStore(path)
    await restarted.initialize({"qq:first", "new-env-user"})

    assert await restarted.get_setting("target_group_openid") == "group-one"
    assert await restarted.list_superusers() == ["second"]
    assert not await restarted.is_superuser("first")
    assert await restarted.is_superuser("qq:second")


async def test_missing_initial_admin_can_be_bootstrapped_later(tmp_path: Path) -> None:
    from src.plugins.runtime_config.database import SettingsStore

    store = SettingsStore(tmp_path / "bot.sqlite3")
    await store.initialize(set())
    assert not await store.is_superuser("anyone")
    await store.initialize({"admin"})
    with pytest.raises(ValueError, match="最后"):
        await store.remove_superuser("admin")
    assert await store.list_superusers() == ["admin"]


async def test_setting_validation_and_group_deduplication(tmp_path: Path) -> None:
    from src.plugins.runtime_config.database import SettingsStore

    store = SettingsStore(tmp_path / "bot.sqlite3")
    await store.initialize({"admin"})
    for key, value in [
        ("QQ_SECRET", "should-not-write"),
        ("TARGET_GROUP_OPENID", "one,two"),
        ("TARGET_GROUP_OPENID", "has space"),
        ("KUMA_PUSH_URL", "file:///etc/passwd"),
        ("KUMA_PUSH_URL", "https://"),
        ("KUMA_PUSH_URL", "https://user:password@kuma.example/push"),
    ]:
        with pytest.raises(ValueError):
            await store.set_setting(key, value)
    await store.set_setting("ALERTMANAGER_TANO_GROUP_OPENIDS", "one, two,one")
    assert await store.get_setting("ALERTMANAGER_TANO_GROUP_OPENIDS") == "one,two"
    await store.set_setting("TARGET_GROUP_OPENID", "one")
    await store.set_setting("TARGET_GROUP_OPENID", "")
    assert await store.get_setting("TARGET_GROUP_OPENID") == ""
    assert "QQ_SECRET" not in await store.all_settings()


async def test_named_keys_are_hashed_unique_and_revocable(tmp_path: Path) -> None:
    from src.plugins.runtime_config.database import SettingsStore

    path = tmp_path / "bot.sqlite3"
    store = SettingsStore(path)
    await store.initialize({"admin"})
    await store.add_cloudflare_key("tano", "manual-secret-one", "g1,g2,g1")
    await store.add_cloudflare_key("lanunion", "manual-secret-two", "g3")
    assert await store.cloudflare_targets("manual-secret-one") == ["g1", "g2"]
    assert await store.cloudflare_targets("manual-secret-two") == ["g3"]
    assert await store.cloudflare_targets("wrong-key") == []
    assert await store.cloudflare_targets("") == []
    assert "manual-secret" not in str(await store.list_cloudflare_keys())
    assert b"manual-secret" not in path.read_bytes()
    with pytest.raises(ValueError):
        await store.add_cloudflare_key("tano", "different-secret3", "g4")
    with pytest.raises(ValueError):
        await store.add_cloudflare_key("duplicate", "manual-secret-one", "g4")
    await store.remove_cloudflare_key("tano")
    assert await store.cloudflare_targets("manual-secret-one") == []
    assert await store.cloudflare_targets("manual-secret-two") == ["g3"]


async def test_concurrent_admin_removals_preserve_one_admin(tmp_path: Path) -> None:
    import asyncio

    from src.plugins.runtime_config.database import SettingsStore

    store = SettingsStore(tmp_path / "bot.sqlite3")
    await store.initialize({"one", "two"})
    results = await asyncio.gather(
        store.remove_superuser("one"),
        store.remove_superuser("two"),
        return_exceptions=True,
    )
    assert len(await store.list_superusers()) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1


async def test_unauthorized_commands_neither_disclose_nor_change_config() -> None:
    from src.plugins.runtime_config import store
    from src.plugins.runtime_config.commands import process_command

    for command in ("help", "list", "set TARGET_GROUP_OPENID attacker", "admin list"):
        assert await process_command("ordinary-user", command) is None
    assert await store.get_setting("TARGET_GROUP_OPENID") == "test-openid"


async def test_commands_update_group_and_mask_sensitive_values() -> None:
    from src.plugins.runtime_config import store
    from src.plugins.runtime_config.commands import process_command

    result = await process_command(
        "test-admin", "set TARGET_GROUP_OPENID 当前群", group_openid="current-group"
    )
    assert result and "已保存" in result
    assert await store.get_setting("TARGET_GROUP_OPENID") == "current-group"
    url = "https://kuma.example/api/push/private-token"
    result = await process_command("test-admin", f"set KUMA_PUSH_URL {url}")
    listing = await process_command("test-admin", "list")
    assert result and listing
    assert "private-token" not in result + listing
    assert "current-group" in listing
    await process_command("test-admin", "unset KUMA_PUSH_URL")
    assert await store.get_setting("KUMA_PUSH_URL") == ""


async def test_command_admin_addition_revocation_and_last_admin_protection() -> None:
    from src.plugins.runtime_config.commands import process_command

    await process_command("test-admin", "admin add qq:new-admin")
    assert await process_command("new-admin", "help")
    await process_command("test-admin", "admin remove new-admin")
    assert await process_command("new-admin", "help") is None
    result = await process_command("test-admin", "admin remove test-admin")
    assert result and "最后" in result
    assert await process_command("test-admin", "help")


async def test_command_key_creation_listing_and_revocation() -> None:
    from src.plugins.runtime_config import store
    from src.plugins.runtime_config.commands import process_command

    result = await process_command(
        "test-admin", "cloudflare add tano manual-secret-one 当前群", group_openid="g1"
    )
    assert result and "manual-secret-one" not in result
    assert await store.cloudflare_targets("manual-secret-one") == ["g1"]
    listing = await process_command("test-admin", "cloudflare list")
    assert listing and "tano" in listing and "g1" in listing
    assert "manual-secret-one" not in listing
    await process_command("test-admin", "cloudflare remove tano")
    assert await store.cloudflare_targets("manual-secret-one") == []


@pytest.mark.parametrize(
    "command",
    [
        'set KUMA_PUSH_URL "unterminated',
        "set TARGET_GROUP_OPENID 当前群",
        "set TARGET_GROUP_OPENID",
        "set UNKNOWN some-secret-value",
        "cloudflare add missing",
        "cloudflare add name tiny-secret g1",
        "unknown something-private",
    ],
)
async def test_invalid_commands_are_safe_and_explain_usage(command: str) -> None:
    from src.plugins.runtime_config import store
    from src.plugins.runtime_config.commands import process_command

    result = await process_command("test-admin", command)
    assert result
    assert "some-secret-value" not in result
    assert "something-private" not in result
    assert await store.get_setting("TARGET_GROUP_OPENID") == "test-openid"


async def test_reads_wait_for_startup_initialization(tmp_path: Path) -> None:
    import asyncio

    from src.plugins.runtime_config.database import SettingsStore

    store = SettingsStore(tmp_path / "fresh.sqlite3")
    reading = asyncio.create_task(store.get_setting("KUMA_PUSH_URL"))
    try:
        await asyncio.sleep(0.01)
        assert not reading.done()
        await store.initialize({"admin"})
        assert await asyncio.wait_for(reading, timeout=1) == ""
    finally:
        if not reading.done():
            reading.cancel()


def test_management_event_logs_do_not_disclose_secrets() -> None:
    from nonebot import logger

    messages: list[str] = []
    handler = logger.add(
        lambda message: messages.append(str(message)), format="{message}"
    )
    try:
        logger.info("QQ event: /配置 cloudflare add tano private-secret-value g1")
        logger.info("QQ payload: /bot-config set KUMA_PUSH_URL https://example/private")
        logger.info("ordinary message remains visible")
    finally:
        logger.remove(handler)
    output = "\n".join(messages)
    assert "private-secret-value" not in output
    assert "https://example/private" not in output
    assert "ordinary message remains visible" in output
