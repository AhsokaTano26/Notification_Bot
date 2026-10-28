"""Hide incoming management commands before NoneBot writes event logs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loguru import Record

# NoneBot accepts commands without separating whitespace, and event repr escapes
# tabs/newlines. Hiding the entire record also covers both of those forms.
MANAGEMENT_COMMAND = re.compile(r"配置|bot-config", re.IGNORECASE)


def redact_management_log(record: Record) -> None:
    """Cover framework event and adapter payload logs, including custom sinks."""
    message = record["message"].replace(r"\u914d\u7f6e", "配置")
    if MANAGEMENT_COMMAND.search(message):
        record["message"] = "[QQ 管理命令内容已隐藏]"
        record["exception"] = None
