"""Shared pytest setup for the notification bot plugins.

Importing any plugin module runs ``nonebot.get_plugin_config``, which needs
NoneBot to be initialized first. Doing that once here keeps every test module
free of that boilerplate.

The keyword arguments win over any ``.env`` file, so a developer's real group
OpenIDs never leak into test assertions.
"""

import nonebot

nonebot.init(
    driver="~fastapi",
    target_group_openid="test-openid",
    target_group_lanunion_openid="test-lanunion-openid",
)
