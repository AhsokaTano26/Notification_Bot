"""NoneBot application entry point."""

import json
import os

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter
from dotenv import load_dotenv


def _get_boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    message = f"{name} must be true or false"
    raise RuntimeError(message)


def configure_qq_adapter() -> None:
    """Convert simple QQ environment variables to the adapter configuration."""
    names = ("QQ_APP_ID", "QQ_TOKEN", "QQ_SECRET")
    credentials = {name: os.getenv(name, "").strip() for name in names}
    if not any(credentials.values()):
        return

    missing = [name for name, value in credentials.items() if not value]
    if missing:
        message = f"Missing required QQ settings: {', '.join(missing)}"
        raise RuntimeError(message)

    os.environ["QQ_BOTS"] = json.dumps(
        [
            {
                "id": credentials["QQ_APP_ID"],
                "token": credentials["QQ_TOKEN"],
                "secret": credentials["QQ_SECRET"],
                "use_websocket": _get_boolean_env("QQ_USE_WEBSOCKET", False),
                "intent": {
                    "c2c_group_at_messages": _get_boolean_env(
                        "QQ_C2C_GROUP_AT_MESSAGES", True
                    )
                },
            }
        ]
    )


load_dotenv(".env")
configure_qq_adapter()


nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(QQAdapter)
nonebot.load_from_toml("pyproject.toml")


if __name__ == "__main__":
    nonebot.run()
