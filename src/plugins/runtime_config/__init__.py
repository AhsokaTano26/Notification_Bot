"""Persistent runtime settings shared by notification plugins."""

from pathlib import Path

from nonebot import get_driver, logger

from .database import SettingsStore
from .logging import redact_management_log

store: SettingsStore = SettingsStore(Path("data/notification_bot.sqlite3"))
logger.configure(patcher=redact_management_log)


@get_driver().on_startup
async def initialize_database() -> None:
    """Create the mounted database and bootstrap initial administrators once."""
    await store.initialize(get_driver().config.superusers)
    if not await store.list_superusers():
        logger.warning("No database superuser; set SUPERUSERS and restart to bootstrap")


from . import commands as commands
