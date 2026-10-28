# 阅后即焚插件实施计划

> **For agentic workers:** Use superpowers:executing-plans for inline implementation.

**Goal:** 在当前 QQ 群用「阅后即焚」开启命令发送者本人的消息 10 秒后自动撤回，用「关闭阅后即焚」关闭本人的开关。

**Architecture:** 新插件通过 NoneBot 事件预处理器监听收到的 `GroupMessageCreateEvent`（含 @ 事件），后台任务调用 QQ `delete_group_message`。状态按 Bot ID、群 OpenID 和发送者 member OpenID 隔离，默认关闭；关闭只取消本人的待执行任务，退出时清理全部任务。计时按消息发送时间扣除传输延迟，异常时间戳回退为接收后 10 秒。不增加依赖。

**Tech Stack:** Python 3.10+、NoneBot 2、QQ adapter、asyncio、pytest。

**Spec:** 用户明确更正撤回对象为开启功能的用户自己的消息；同群不同用户独立控制。

## Global Constraints

- 插件位于 `src/plugins/burn_after_reading/`，由 `nb plugin create` 创建。
- 开关仅在内存中保存，重启默认关闭，不撤回开启前的消息。
- 覆盖已开启用户的普通群消息和 @ 消息，包括开启命令；Bot 消息、Webhook 通知、私聊及其他未开启用户消息不安排任务。
- 需要 QQ 平台允许 Bot 接收群消息并撤回成员消息；仅接收 @ 消息时无法覆盖未投递的普通消息。
- 撤回失败记录日志，不影响发送或其他消息撤回。
- 接受现有命令前缀，并直接支持用户指定的两个无前缀命令。

## Approaches

发送成功钩子仅覆盖 Bot 自己发送的消息，无法实现用户的个人阅后即焚。采用事件预处理器，在其他命令响应器之前为收到的用户消息安排任务，不拦截后续命令处理。

## Review Focus

关闭后重新开启不能恢复旧任务；不同用户、群和 Bot 互不影响；撤回失败不得泄漏后台异常；停机不能遗留任务；Bot 自己发出的消息和通知必须保留。重复投递仅在已有待执行任务时去重。

### Task 1: 独立插件、测试与使用说明

**Files:** 新增 `src/plugins/burn_after_reading/recall.py`、`tests/test_burn_after_reading.py`，完善插件 `__init__.py`，更新 `README.md`。

**Interfaces:** `RecallManager.enable(bot_id, group_id, user_id)`、`async disable(bot_id, group_id, user_id)`、`schedule(bot, event)`、`async shutdown()`；命令处理器与事件预处理器使用同一个实例。

- [x] 先写并运行测试：10 秒计时、时间戳延迟/异常、默认关闭、用户/群/Bot 隔离、重复事件、关闭取消、重新开启、撤回异常与停机清理。
- [x] 实现个人任务管理器与命令，接入事件预处理器，测试真实 NoneBot 事件分发与 QQ Bot 调用边界。
- [x] 更新 README：命令、范围、重启行为、手动 QQ 验证步骤。
- [x] 运行 `.venv/bin/pytest -q`、`.venv/bin/ruff check .`、`.venv/bin/ruff format --check .`、`.venv/bin/pyright`，预期全部通过；检查最终差异。

执行记录：在用户当前工作区完成这项局部新增，按用户后续指令提交并推送。插件骨架已通过 NB CLI 生成；其缓存写入已获执行许可。

验证记录：插件测试已按用户纠正后的个人开关需求重新编写，共 16 项；全项目 65 项测试通过，Ruff lint/format 与 Pyright 均通过。未连接真实 QQ 发送消息。
