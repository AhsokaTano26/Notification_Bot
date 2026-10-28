"""Initialize NoneBot once; give every test a fresh temporary SQLite database."""

from __future__ import annotations

from typing import TYPE_CHECKING

import nonebot
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from src.plugins.runtime_config.database import SettingsStore

nonebot.init(
    driver="~fastapi",
    target_group_openid="test-openid",
    target_group_lanunion_openid="test-lanunion-openid",
    general_webhook_group_openid="test-generic-openid",
    kuma_push_url="",
)

nonebot.load_plugin("src.plugins.runtime_config")


@pytest.fixture(autouse=True)
async def settings_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SettingsStore:
    """Never read production configuration or write the deployment database."""
    from src.plugins import runtime_config
    from src.plugins.runtime_config.database import SettingsStore

    store = SettingsStore(tmp_path / "settings.sqlite3")
    await store.initialize({"test-admin"})
    await store.set_setting("TARGET_GROUP_OPENID", "test-openid")
    await store.set_setting("TARGET_GROUP_LANUNION_OPENID", "test-lanunion-openid")
    await store.set_setting("GENERAL_WEBHOOK_GROUP_OPENID", "test-generic-openid")
    monkeypatch.setattr(runtime_config, "store", store)
    return store
