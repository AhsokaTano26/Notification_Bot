# 扩展 Uptime Kuma 通知：新增 `/uptime-kuma/lanunion` 路由 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Uptime Kuma 通知新增一条 `/uptime-kuma/lanunion` 路由，把 webhook 发往 `TARGET_GROUP_LANUNION_OPENID` 对应的 QQ 群。

**Architecture:** 在现有 `src/plugins/uptime_kuma/` 插件内做参数化：把 `handle_uptime_kuma_webhook` 的函数体抽成 `_forward_uptime_kuma_webhook(request, target_group_openid)`，再为两条路由各写一个一行包装 handler，各自绑定自己的 config 字段，最后注册第二个 `HTTPServerSetup`。这与 `src/plugins/alertmanager_webhook/__init__.py` 已有的双路由写法一致，格式化逻辑只保留一份。

**Tech Stack:** Python 3.10+，NoneBot 2，nonebot-adapter-qq，FastAPI 驱动，pydantic v2，pytest + pytest-asyncio。

设计文档：`docs/superpowers/specs/2026-09-15-uptime-kuma-lanunion-route-design.md`

## Global Constraints

以下约束适用于每一个 task，逐条照做：

- **单群，不做逗号分隔。** 每条路由只接收一个 group OpenID，不引入 `_group_openids` 之类的解析。
- **两个配置项均为必填。** `target_group_openid` 与 `target_group_lanunion_openid` 都用 `Field(min_length=1)`，缺失时进程启动阶段抛 pydantic `ValidationError`。
- **监控面板链接保持硬编码** 为 `https://status.tano.asia/dashboard/{monitor_id}`，不新增配置项。
- **不新增 `route_name` 参数**。本插件配置为必填，不存在 Alertmanager 里那个"未配置"的 503 分支。
- **不改动任何格式化逻辑**：`_uptime_kuma_notification`、`CERTIFICATE_EXPIRY_PATTERN`、`_status`、`_certificate_expiry_status`、`_notification_fields` 全部保持原样。
- **`handle_uptime_kuma_webhook` 的名字、docstring、对外行为不变。**
- **代码风格**：4 空格缩进，行宽 88（`ruff format` 为准），类型注解齐全。

### 既有基线：这些"错误"是预期的，不是你引入的

改动前仓库本身就不干净，实测确认：

| 命令 | 改动前 | 改动后预期 |
|---|---|---|
| `ruff check .` | 15 errors | **仍是 15 errors**。其中 `src/plugins/uptime_kuma/__init__.py` 的 2 个 `BLE001`（`except Exception`）会随代码原样搬进新函数，数量和内容都不变，**不得新增**。 |
| `ruff format --check .` | 1 file would be reformatted (`src/plugins/group_tools/__init__.py`) | **仍只有这一个文件**。`src/plugins/uptime_kuma/__init__.py` 必须保持"already formatted"。 |
| `pyright --pythonpath .venv/bin/python` | 3 errors | **4 errors**。新增的 1 个是 `setup_http_server` 的 `reportAttributeAccessIssue`，与既有 3 个同源（NoneBot 类型存根问题），属于预期。 |
| `pytest` | 无法运行 | 全部通过 |

不要把既有的 15 个 ruff 错误或 4 个 pyright 错误当成自己的问题去修——那是独立的清理工作，不在本计划范围内。

### 工具位置

`ruff` 与 `pyright` 装在系统 Python 3.11 下，不在 venv 里：

```bash
export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:$PATH"
```

`pytest` 需要装进项目 venv（Task 1 会做）。所有 pytest 命令都用 `.venv/bin/python -m pytest` 调用。

---

## File Structure

| 文件 | 职责 | 本计划中的动作 |
|---|---|---|
| `src/plugins/uptime_kuma/__init__.py` | Uptime Kuma 两条路由的全部逻辑：webhook 解析、消息格式化、发送 | 修改（Config、抽函数、加 handler、加路由） |
| `tests/conftest.py` | 测试期一次性初始化 NoneBot 并注入必填配置 | 新建 |
| `tests/test_uptime_kuma.py` | Uptime Kuma 格式化与路由测试 | 修改（补 3 个路由测试） |
| `pyproject.toml` | 依赖与工具配置 | 修改（dev 依赖 + pytest 配置） |
| `.env.example` | 环境变量说明 | 修改（新增一个变量） |
| `README.md` | 使用文档 | 修改（Uptime Kuma 章节 + QQ Webhook 章节） |

---

## Task 1: 测试基础设施

修复 `tests/` 当前无法运行的问题。**这是一个独立可交付的单元**：做完之后，仓库里已有的两个格式化测试就能跑通，无需任何插件改动。

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Test: `tests/test_uptime_kuma.py`（已存在，本 task 不修改它）

**Interfaces:**
- Consumes: 无
- Produces: 一个已初始化的 NoneBot 全局环境，其中 `target_group_openid="test-openid"`、`target_group_lanunion_openid="test-lanunion-openid"` 可供后续所有测试使用。

- [ ] **Step 1: 在 `pyproject.toml` 的 dev 依赖中加入 pytest**

把 `[project.optional-dependencies]` 段改成：

```toml
[project.optional-dependencies]
dev = [
    "pyright[nodejs]",
    "ruff",
    "pytest",
    "pytest-asyncio",
]
```

- [ ] **Step 2: 在 `pyproject.toml` 中加入 pytest 配置**

追加到文件末尾：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
```

`pythonpath = ["."]` 不是可选优化。`src/` 与 `tests/` 下都没有 `__init__.py`，二者都是命名空间包，测试通过 `from src.plugins... import ...` 导入模块。缺少这一项时，pytest 默认的 `prepend` 导入模式只会把 `tests/` 目录放进 `sys.path`，不会放仓库根目录，`pytest tests/` 会直接报 `ModuleNotFoundError: No module named 'src'`。

- [ ] **Step 3: 创建 `tests/conftest.py`**

```python
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
```

- [ ] **Step 4: 安装新增的开发依赖**

```bash
.venv/bin/python -m pip install pytest pytest-asyncio
```

预期：安装成功，无报错。

- [ ] **Step 5: 运行已有测试，确认基础设施修好了**

```bash
.venv/bin/python -m pytest tests/ -q
```

预期输出：

```
2 passed
```

这两个测试此前**根本无法收集**（导入插件时就抛 `ValueError: NoneBot has not been initialized`）。现在通过，说明 conftest 生效。

- [ ] **Step 6: 确认没有动到源码**

```bash
git status --short src/
```

预期：**无任何输出**。本 task 不应触碰 `src/` 下任何文件。

（不要直接跑 `git status --short`——工作区里本来就存在与本次任务无关的未提交内容：`.env.example` 的 M 状态，以及 `.DS_Store`、`src/.DS_Store` 两个未跟踪文件。它们应当在整轮改动结束后依然原封不动，既不要提交也不要删除。）

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "test: 修复测试基础设施，让插件测试可运行

tests/ 此前无法运行：导入插件会触发 get_plugin_config，缺少
nonebot.init() 时直接抛异常，且环境未安装 pytest。

新增 conftest.py 完成一次性初始化并注入必填配置，补齐 pytest 与
pytest-asyncio 依赖。pythonpath = [\".\"] 是必需的——src/ 与 tests/
均为命名空间包，缺少它时 pytest 不会把仓库根目录放进 sys.path。"
```

---

## Task 2: 插件新增 lanunion 路由

用 TDD 实现核心改动。

**Files:**
- Modify: `src/plugins/uptime_kuma/__init__.py`
- Test: `tests/test_uptime_kuma.py`

**Interfaces:**
- Consumes: Task 1 建立的测试环境（`target_group_openid="test-openid"`、`target_group_lanunion_openid="test-lanunion-openid"`）
- Produces:
  - `Config.target_group_lanunion_openid: str`
  - `_forward_uptime_kuma_webhook(request: Request, target_group_openid: str) -> Response`
  - `handle_lanunion_uptime_kuma_webhook(request: Request) -> Response`
  - HTTP 路由 `POST /uptime-kuma/lanunion`（名称 `uptime-kuma-lanunion-webhook`）

- [ ] **Step 1: 写失败的测试**

把 `tests/test_uptime_kuma.py` 整个文件替换为下面的内容。原有的两个格式化测试原样保留，只新增导入、三个辅助类和三个路由测试。

```python
"""Tests for Uptime Kuma notification formatting and routing."""

from typing import Any, ClassVar

import pytest

from src.plugins import uptime_kuma
from src.plugins.uptime_kuma import _uptime_kuma_notification

HTTP_OK = 200


class FakeBot:
    """Records group messages instead of sending them to QQ."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []

    async def send_to_group(self, group_openid: str, message: Any) -> None:
        self.sent.append((group_openid, message))


class FakeRequest:
    """Minimal stand-in for nonebot.drivers.Request."""

    json: ClassVar[Any] = {"msg": "Disk usage alert"}
    content: ClassVar[bytes] = b""
```

这段开头有两个容易踩空、且已被 ruff 实测校验过的细节，请逐字照抄：

- `import pytest` 与 `from src.plugins import ...` 之间**必须有空行**。仓库根目录存在 `src/`，ruff 据此把 `src` 判为 first-party，与 `pytest` 分属两组。少这个空行会触发 `I001`。（注意：只有在缺少 `src/` 目录的临时目录里跑 ruff 才会得出相反结论，别被误导。）
- `HTTP_OK = 200` 常量是必需的，直接写 `== 200` 会触发 `PLR2004`（magic value）。


def test_formats_certificate_expiry_message() -> None:
    markdown, plain_text = _uptime_kuma_notification(
        {
            "msg": (
                "[Tano博客（国内）][https://tano.asia] server certificate "
                "tano.asia will expire in 21 days"
            ),
        },
        b"",
    )

    assert "**🟡 Tano博客（国内） · 证书即将到期**" in markdown
    assert "地址：https://tano.asia" in markdown
    assert "证书域名：tano.asia" in markdown
    assert "剩余时间：21 天" in markdown
    assert "🟡 Tano博客（国内） · 证书即将到期" in plain_text


def test_formats_urgent_certificate_expiry_message() -> None:
    markdown, _ = _uptime_kuma_notification(
        {
            "msg": (
                "[Tano博客（国内）][https://tano.asia] server certificate "
                "tano.asia will expire in 7 days"
            ),
        },
        b"",
    )

    assert "**🔴 Tano博客（国内） · 证书即将到期**" in markdown


async def test_default_route_sends_to_default_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(uptime_kuma, "_get_qq_bot", lambda: bot)

    response = await uptime_kuma.handle_uptime_kuma_webhook(FakeRequest())

    assert response.status_code == HTTP_OK
    assert [openid for openid, _ in bot.sent] == ["test-openid"]


async def test_lanunion_route_sends_to_lanunion_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    monkeypatch.setattr(uptime_kuma, "_get_qq_bot", lambda: bot)

    response = await uptime_kuma.handle_lanunion_uptime_kuma_webhook(FakeRequest())

    assert response.status_code == HTTP_OK
    assert [openid for openid, _ in bot.sent] == ["test-lanunion-openid"]
```

`monkeypatch.setattr(..., lambda: bot)` 里必须用**闭包捕获同一个 `bot` 实例**。不要写成 `lambda: FakeBot()`——那样每次调用都会新建一个空对象，`bot.sent` 将永远是空的，测试会假绿。同理也不要直接传 `FakeBot` 类（会触发 `PLW0108`）。

> **不要为"空请求体返回 400"写测试。** 设计文档最初假设空 body 会命中 `return _json_response(400, ...)`，实测证明**该分支是死代码**：`_uptime_kuma_notification(None, b"")` 的返回值为 `'⚪ Uptime Kuma · 未知状态'`，非空——因为 `plain_text` 永远带着图标 + `Uptime Kuma` + 状态这一行表头。所以空 body 会一路走到 `_get_qq_bot()`，返回 200 或 503，绝不会是 400（已对照未改动的原插件确认）。详见设计文档"错误处理"一节。


两个路由测试的设计意图：直接锁定本次改动的核心风险——**路由与配置字段的绑定关系**（lanunion 的请求绝不能发到默认群）。两者全程不依赖真实 QQ 凭据。

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_uptime_kuma.py -q
```

预期：**3 passed, 1 failed**。

失败的只有 `test_lanunion_route_sends_to_lanunion_group`（缺少新函数）：

```
AttributeError: module 'src.plugins.uptime_kuma' has no attribute 'handle_lanunion_uptime_kuma_webhook'
```

这是 TDD 里正常且预期的形态。`test_default_route_sends_to_default_group` **在实现之前就会通过**——它断言的是 `/uptime-kuma` 现有行为，作用是给这次重构上一道防回归的锁（抽函数时若把默认路由的配置字段接错，它立刻会红）。不要因为它"一开始就是绿的"就以为写错了测试。

如果你的失败原因不是 `AttributeError`（比如 `ModuleNotFoundError` 或 `ValidationError`），说明 Task 1 没做对，先回去修。

- [ ] **Step 3: 给 Config 加上 lanunion 字段**

在 `src/plugins/uptime_kuma/__init__.py` 中，把 Config 类改成：

```python
class Config(BaseModel):
    """Plugin settings loaded from the NoneBot environment."""

    target_group_openid: str = Field(min_length=1)
    target_group_lanunion_openid: str = Field(min_length=1)
```

- [ ] **Step 4: 抽出核心发送函数并新增两个包装 handler**

把文件末尾从 `async def handle_uptime_kuma_webhook(request: Request) -> Response:` 起，直到第一个 `get_driver().setup_http_server(...)` 调用结束为止的整段，替换为下面的内容。

改动实质只有一处：原函数体里的两处 `config.target_group_openid` 变成函数参数 `target_group_openid`。其余逻辑、日志文案、状态码逐字不变。

```python
async def _forward_uptime_kuma_webhook(
    request: Request,
    target_group_openid: str,
) -> Response:
    """Forward an Uptime Kuma webhook to one configured group."""

    markdown, message = _uptime_kuma_notification(request.json, request.content)
    if not message:
        return _json_response(400, {"detail": "webhook body is empty"})

    qq_bot = _get_qq_bot()
    if qq_bot is None:
        logger.warning("Uptime Kuma webhook received before the QQ bot connected")
        return _json_response(503, {"detail": "QQ bot is not connected"})

    try:
        await qq_bot.send_to_group(
            group_openid=target_group_openid,
            message=MessageSegment.markdown(markdown),
        )
    except Exception:
        logger.warning("QQ Markdown notification failed; sending plain text instead")
        try:
            await qq_bot.send_to_group(
                group_openid=target_group_openid,
                message=message[:1900],
            )
        except Exception:
            logger.exception("Failed to forward Uptime Kuma webhook to QQ group")
            return _json_response(502, {"detail": "failed to send QQ group message"})

    return _json_response(200, {"status": "forwarded"})


async def handle_uptime_kuma_webhook(request: Request) -> Response:
    """Forward an Uptime Kuma webhook to the configured group."""
    return await _forward_uptime_kuma_webhook(request, config.target_group_openid)


async def handle_lanunion_uptime_kuma_webhook(request: Request) -> Response:
    """Forward a Lanunion Uptime Kuma webhook to its configured group."""
    return await _forward_uptime_kuma_webhook(
        request, config.target_group_lanunion_openid
    )


get_driver().setup_http_server(
    HTTPServerSetup(
        path=URL("/uptime-kuma"),
        method="POST",
        name="uptime-kuma-webhook",
        handle_func=handle_uptime_kuma_webhook,
    )
)
get_driver().setup_http_server(
    HTTPServerSetup(
        path=URL("/uptime-kuma/lanunion"),
        method="POST",
        name="uptime-kuma-lanunion-webhook",
        handle_func=handle_lanunion_uptime_kuma_webhook,
    )
)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/ -q
```

预期输出：

```
4 passed
```

- [ ] **Step 6: 跑格式与类型检查**

```bash
export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:$PATH"

ruff check tests/
ruff check src/plugins/uptime_kuma/__init__.py
ruff format --check src/plugins/uptime_kuma/__init__.py tests/
pyright --pythonpath .venv/bin/python
```

预期：

- `ruff check tests/` → **`All checks passed!`**。`tests/` 下新增的代码必须零告警。注意这一条在本计划里是单独跑的，**不要**用仓库根目录的 `ruff check .` 代替——那样会混进 15 个既有错误，看不出自己有没有引入新问题。
- `ruff check src/plugins/uptime_kuma/__init__.py` → **恰好 2 个 `BLE001`**，行号变了但内容与改动前一致（两个 `except Exception`）。**出现任何其他规则即为你引入的问题，必须修掉。**
- `ruff format --check` → `2 files already formatted`（若报 would reformat，跑 `ruff format <该文件>` 后重跑）。
- `pyright --pythonpath .venv/bin/python` → **4 errors**，全部是 `setup_http_server` 的 `reportAttributeAccessIssue`。改动前是 3 个，新增的 1 个对应新增的那次 `setup_http_server` 调用，与既有模式同源，属预期。

- [ ] **Step 7: Commit**

```bash
git add src/plugins/uptime_kuma/__init__.py tests/test_uptime_kuma.py
git commit -m "feat: Uptime Kuma 通知支持 /uptime-kuma/lanunion 路由

把 handler 函数体抽成 _forward_uptime_kuma_webhook(request,
target_group_openid)，两条路由各由一个薄包装绑定自己的配置字段，
新增 TARGET_GROUP_LANUNION_OPENID（必填）。

格式化与证书到期逻辑保持单一实现，两路由共用。"
```

---

## Task 3: 文档更新

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 定义的配置项名 `TARGET_GROUP_LANUNION_OPENID` 与路由路径 `/uptime-kuma/lanunion`
- Produces: 无（终端交付物）

- [ ] **Step 1: 更新 `.env.example`**

把这三行的位置：

```
# 在目标群中使用 /群信息 命令，以获取 TARGET_GROUP_OPENID。

TARGET_GROUP_OPENID=replace-with-group-openid
```

替换为：

```
# 在目标群中使用 /群信息 命令，以获取目标群 OpenID。
# /uptime-kuma
TARGET_GROUP_OPENID=replace-with-group-openid
# /uptime-kuma/lanunion
TARGET_GROUP_LANUNION_OPENID=replace-with-lanunion-group-openid
```

- [ ] **Step 2: 更新 README 的 Uptime Kuma 章节**

把 `## Uptime Kuma Webhook` 章节开头到第 2 步为止的内容，替换为：

```markdown
## Uptime Kuma Webhook

Uptime Kuma sends its Webhook notification payload to one of two routes:

- `POST https://<your-host>/uptime-kuma` uses `TARGET_GROUP_OPENID`.
- `POST https://<your-host>/uptime-kuma/lanunion` uses
  `TARGET_GROUP_LANUNION_OPENID`.

Each variable holds a single group OpenID; they are not comma-separated. Both
are required — the bot refuses to start when either is missing.

1. Copy `.env.example` to `.env` and fill in the QQ Official Bot credentials:
   `QQ_APP_ID`, `QQ_TOKEN`, and `QQ_SECRET`. Keep
   `QQ_C2C_GROUP_AT_MESSAGES=true`; it is required for group command events.
   In each destination QQ group, send `/群信息` and use the returned **群 OpenID**
   as that route's variable; this is not the visible QQ group number.
2. In Uptime Kuma, create a Webhook notification pointing to the route whose
   group should receive it, for example `POST https://<your-host>/uptime-kuma/lanunion`.
```

该章节中后续两段（以 `For Uptime Kuma's default JSON body,` 开头的一段，以及以 `Certificate-expiry messages in Uptime Kuma's default form` 开头的一段）**保持原样，一个字都不改**。

- [ ] **Step 3: 更新 README 的 QQ Webhook 章节**

该章节末尾这句：

```
uses `QQ_SECRET` to verify signed events. The same domain receives both paths:
`/qq/webhook` for QQ and `/uptime-kuma` for Uptime Kuma.
```

替换为：

```
uses `QQ_SECRET` to verify signed events. The same domain receives every path:
`/qq/webhook` for QQ, `/uptime-kuma` and `/uptime-kuma/lanunion` for Uptime
Kuma, and `/alert/lanunion` and `/alert/tano` for Alertmanager.
```

- [ ] **Step 4: 更新 README 的 Docker 章节**

该章节倒数第二句：

```
before exposing `/qq/webhook` and `/uptime-kuma` to the internet. Stop it with
```

替换为：

```
before exposing `/qq/webhook` and the Uptime Kuma webhook paths to the
internet. Stop it with
```

- [ ] **Step 5: 校验文档里的环境变量真的能映射到配置字段**

这是防手滑的关键检查——文档写了变量名但代码没实现、或大小写对不上，是本类改动最常见的失误。直接用一个真实环境变量验证端到端映射：

```bash
TARGET_GROUP_LANUNION_OPENID=probe .venv/bin/python -c "
import nonebot
nonebot.init(driver='~fastapi', target_group_openid='ok')
import src.plugins.uptime_kuma as m
assert m.config.target_group_lanunion_openid == 'probe', m.config
print('环境变量映射 OK')
"
```

预期：输出 `环境变量映射 OK`。

必须用**真实环境变量**传入 `TARGET_GROUP_LANUNION_OPENID`，不要写成 `nonebot.init(TARGET_GROUP_LANUNION_OPENID=...)`。已实测：pydantic-settings 的大小写不敏感匹配只作用于环境变量源，`init()` 的关键字参数必须用精确字段名（小写），传大写会被判为字段缺失并抛 `ValidationError: target_group_openid Field required`。这也正是 `tests/conftest.py` 里用 `target_group_openid=` 小写形式的原因。

再核对字面量出现次数：

```bash
grep -rc "TARGET_GROUP_LANUNION_OPENID" .env.example README.md
grep -rc "uptime-kuma/lanunion" .env.example README.md
grep -c "target_group_lanunion_openid" src/plugins/uptime_kuma/__init__.py
```

预期（已按本计划的替换文本逐字模拟过）：

| 文件 | `TARGET_GROUP_LANUNION_OPENID` | `uptime-kuma/lanunion` | `target_group_lanunion_openid` |
|---|---|---|---|
| `.env.example` | 1 | 1 | — |
| `README.md` | 1 | 3 | — |
| `src/plugins/uptime_kuma/__init__.py` | — | 1 | 2 |

插件源码里变量名命中 2 行（Config 字段声明 + handler 中引用），且全部是小写——大写形式只出现在文档中，两边的对应关系由 NoneBot 自动完成，Step 5 上半段的实测就是在验证这条链路。

- [ ] **Step 6: Commit**

```bash
git add .env.example README.md
git commit -m "docs: 补充 /uptime-kuma/lanunion 路由说明

.env.example 新增 TARGET_GROUP_LANUNION_OPENID，README 的 Uptime Kuma
章节改为说明两条路由，并同步 QQ Webhook 与 Docker 章节里列举的路径。"
```

---

## 完成后的人工验收

自动化测试覆盖不到"路由真的注册到 FastAPI 上"这件事（测试直接调用 handler 函数）。以下步骤补上这一段。

- [ ] **Step 1: 启动服务**

需要一个可用的 `.env`（QQ 凭据可填占位值，路由注册不依赖它们）：

```bash
.venv/bin/python bot.py
```

- [ ] **Step 2: 探测路由是否注册**

关键判断标准是**「不是 404」**，而不是某个具体状态码——只要响应来自我们的 handler，就证明路由挂上了。

```bash
for p in /uptime-kuma /uptime-kuma/lanunion /uptime-kuma/unknown; do
  printf '%-26s -> %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8080$p)"
done
```

预期：

| 路径 | 状态码 | 说明 |
|---|---|---|
| `/uptime-kuma` | `503` | 路由已注册，走到 QQ bot 连接检查 |
| `/uptime-kuma/lanunion` | `503` | 同上，这就是本次新增的路由 |
| `/uptime-kuma/unknown` | `404` | 对照组，证明 503 确实来自我们的 handler |

`503` 的响应体为 `{"detail": "QQ bot is not connected"}`，说明请求已被我们的 handler 接收并解析。

**不要期待 400。** 空 body 并不会命中 `webhook body is empty` 分支——那个分支是死代码（详见设计文档"错误处理"）。如果你看到 400，说明代码与设计不符，需要停下来核对。

同样地，具体状态码取决于环境：若 `.env` 里的 QQ 凭据可用，bot 会成功连接，此时前两条会变成 200（或发送失败时的 502）。判据始终是那条对照线——**新路径不能是 404**。

- [ ] **Step 3: 端到端验证**

在 Uptime Kuma 中新建一个 Webhook 通知，指向 `https://<host>/uptime-kuma/lanunion`，触发一次测试通知，确认消息落在 lanunion 群，且"查看监控"链接指向 `https://status.tano.asia/dashboard/<id>`。
