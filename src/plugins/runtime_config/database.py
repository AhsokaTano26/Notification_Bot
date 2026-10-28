"""SQLite configuration, administrator identities and hashed webhook secrets."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, TypeVar
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

T = TypeVar("T")
SETTING_KEYS = (
    "TARGET_GROUP_OPENID",
    "TARGET_GROUP_LANUNION_OPENID",
    "ALERTMANAGER_LANUNION_GROUP_OPENIDS",
    "ALERTMANAGER_TANO_GROUP_OPENIDS",
    "GENERAL_WEBHOOK_GROUP_OPENID",
    "KUMA_PUSH_URL",
)
MULTI_GROUP_KEYS = frozenset(
    {"ALERTMANAGER_LANUNION_GROUP_OPENIDS", "ALERTMANAGER_TANO_GROUP_OPENIDS"}
)
KEY_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_IDENTIFIER_LENGTH = 256
MIN_SECRET_LENGTH = 16
MAX_SECRET_LENGTH = 256


def normalize_user_id(user_id: str) -> str:
    """Accept raw QQ OpenIDs and NoneBot's qq: prefixed form."""
    value = user_id.strip().removeprefix("qq:")
    if (
        not value
        or len(value) > MAX_IDENTIFIER_LENGTH
        or any(character.isspace() or character in ",:" for character in value)
    ):
        message = "QQ 用户 OpenID 无效"
        raise ValueError(message)
    return value


def group_openids(value: str) -> list[str]:
    """Validate and deduplicate comma-separated group OpenIDs."""
    parts = [part.strip() for part in value.split(",")]
    if any(
        not part
        or len(part) > MAX_IDENTIFIER_LENGTH
        or any(character.isspace() or not character.isprintable() for character in part)
        for part in parts
    ):
        message = "群 OpenID 无效，请使用英文逗号分隔多个群"
        raise ValueError(message)
    return list(dict.fromkeys(parts))


def _setting_key(key: str) -> str:
    key = key.upper()
    if key not in SETTING_KEYS:
        message = "未知配置项，请使用 /配置 help 查看"
        raise ValueError(message)
    return key


def _setting_value(key: str, value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if key == "KUMA_PUSH_URL":
        try:
            url = urlsplit(value)
            valid = (
                url.scheme in {"http", "https"}
                and bool(url.hostname)
                and url.username is None
                and url.password is None
                and not url.fragment
                and not any(character.isspace() for character in value)
            )
            _ = url.port  # Validate malformed port numbers as well.
        except ValueError:
            valid = False
        if not valid:
            message = "Kuma Push URL 必须是有效的 HTTP(S) 地址，不能含登录凭据"
            raise ValueError(message)
        return value
    groups = group_openids(value)
    if key not in MULTI_GROUP_KEYS and len(groups) != 1:
        message = "此配置项仅支持一个群 OpenID"
        raise ValueError(message)
    return ",".join(groups)


def _secret_hash(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


class SettingsStore:
    """Use short transactions on independent connections off the event loop."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ready = asyncio.Event()

    async def _run(
        self,
        operation: Callable[[sqlite3.Connection], T],
        *,
        write: bool = False,
        initializing: bool = False,
    ) -> T:
        if not initializing:
            await self._ready.wait()

        def execute() -> T:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with (
                closing(sqlite3.connect(self.path, timeout=10)) as connection,
                connection,
            ):
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                return operation(connection)

        return await asyncio.to_thread(execute)

    async def initialize(self, superusers: Iterable[str]) -> None:
        """Bootstrap once, so restart cannot restore a revoked administrator."""
        users = sorted({normalize_user_id(user_id) for user_id in superusers})

        def initialize(connection: sqlite3.Connection) -> None:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS settings "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS superusers (user_id TEXT PRIMARY KEY)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS cloudflare_keys "
                "(name TEXT PRIMARY KEY, secret_hash BLOB NOT NULL UNIQUE, "
                "groups_json TEXT NOT NULL)"
            )
            seeded = connection.execute(
                "SELECT 1 FROM metadata WHERE key = 'superusers_initialized'"
            ).fetchone()
            if users and not seeded:
                connection.executemany(
                    "INSERT OR IGNORE INTO superusers VALUES (?)",
                    [(user_id,) for user_id in users],
                )
                connection.execute(
                    "INSERT INTO metadata VALUES ('superusers_initialized', '1')"
                )

        await self._run(initialize, write=True, initializing=True)
        self._ready.set()

    async def get_setting(self, key: str) -> str:
        """Read a current setting; absent settings are disabled."""
        key = _setting_key(key)

        def read(connection: sqlite3.Connection) -> str:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else ""

        return await self._run(read)

    async def all_settings(self) -> dict[str, str]:
        """Return a single snapshot including unset supported settings."""

        def read(connection: sqlite3.Connection) -> dict[str, str]:
            values = dict(connection.execute("SELECT key, value FROM settings"))
            return {key: values.get(key, "") for key in SETTING_KEYS}

        return await self._run(read)

    async def set_setting(self, key: str, value: str) -> None:
        """Validate and replace one supported runtime setting atomically."""
        key = _setting_key(key)
        value = _setting_value(key, value)

        def write(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT INTO settings VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

        await self._run(write, write=True)

    async def list_superusers(self) -> list[str]:
        """Return persisted QQ administrator identities."""
        return await self._run(
            lambda connection: [
                row[0]
                for row in connection.execute(
                    "SELECT user_id FROM superusers ORDER BY user_id"
                )
            ]
        )

    async def is_superuser(self, user_id: str) -> bool:
        """Check authorization against the current database, never env roles."""
        try:
            user_id = normalize_user_id(user_id)
        except ValueError:
            return False
        return await self._run(
            lambda connection: (
                connection.execute(
                    "SELECT 1 FROM superusers WHERE user_id = ?", (user_id,)
                ).fetchone()
                is not None
            )
        )

    async def add_superuser(self, user_id: str) -> None:
        """Add a QQ OpenID; repeated additions are harmless."""
        user_id = normalize_user_id(user_id)

        def write(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT OR IGNORE INTO superusers VALUES (?)", (user_id,)
            )

        await self._run(write, write=True)

    async def remove_superuser(self, user_id: str) -> None:
        """Prevent lockout even when two removal commands run concurrently."""
        user_id = normalize_user_id(user_id)

        def write(connection: sqlite3.Connection) -> None:
            exists = connection.execute(
                "SELECT 1 FROM superusers WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not exists:
                raise ValueError("超级管理员不存在")
            count = connection.execute("SELECT COUNT(*) FROM superusers").fetchone()[0]
            if count <= 1:
                raise ValueError("不能删除最后一位超级管理员")
            connection.execute("DELETE FROM superusers WHERE user_id = ?", (user_id,))

        await self._run(write, write=True)

    async def add_cloudflare_key(self, name: str, secret: str, groups: str) -> None:
        """Create a manually supplied, named secret without storing plaintext."""
        if not KEY_NAME.fullmatch(name):
            message = "密钥名称仅支持 1-64 个英文字母、数字、下划线或连字符"
            raise ValueError(message)
        if not MIN_SECRET_LENGTH <= len(secret) <= MAX_SECRET_LENGTH or any(
            not "!" <= character <= "~" for character in secret
        ):
            message = "密钥须为 16-256 个非空格可打印 ASCII 字符"
            raise ValueError(message)
        targets = group_openids(groups)

        def write(connection: sqlite3.Connection) -> None:
            try:
                connection.execute(
                    "INSERT INTO cloudflare_keys VALUES (?, ?, ?)",
                    (name, _secret_hash(secret), json.dumps(targets)),
                )
            except sqlite3.IntegrityError:
                raise ValueError("密钥名称或密钥已存在，请先删除再添加") from None

        await self._run(write, write=True)

    async def list_cloudflare_keys(self) -> dict[str, list[str]]:
        """List only names and destination groups, without secret material."""
        return await self._run(
            lambda connection: {
                name: json.loads(groups)
                for name, groups in connection.execute(
                    "SELECT name, groups_json FROM cloudflare_keys ORDER BY name"
                )
            }
        )

    async def remove_cloudflare_key(self, name: str) -> None:
        """Revoke a key immediately for subsequent requests."""

        def write(connection: sqlite3.Connection) -> None:
            result = connection.execute(
                "DELETE FROM cloudflare_keys WHERE name = ?", (name,)
            )
            if not result.rowcount:
                raise ValueError("密钥名称不存在")

        await self._run(write, write=True)

    async def cloudflare_targets(self, secret: str) -> list[str]:
        """Match a high entropy secret by digest, without comparing plaintext."""
        if not MIN_SECRET_LENGTH <= len(secret) <= MAX_SECRET_LENGTH:
            return []

        def read(connection: sqlite3.Connection) -> list[str]:
            row = connection.execute(
                "SELECT groups_json FROM cloudflare_keys WHERE secret_hash = ?",
                (_secret_hash(secret),),
            ).fetchone()
            return json.loads(row[0]) if row else []

        return await self._run(read)
