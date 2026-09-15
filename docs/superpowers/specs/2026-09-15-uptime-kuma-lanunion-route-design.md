# 扩展 Uptime Kuma 通知：新增 `/uptime-kuma/lanunion` 路由

日期：2026-09-15
状态：已确认，待实现

## 背景与目标

当前通知系统有三条入站路由：

| 路由 | 配置变量 | 用途 |
|---|---|---|
| `/uptime-kuma` | `TARGET_GROUP_OPENID` | Uptime Kuma 通知 |
| `/alert/lanunion` | `ALERTMANAGER_LANUNION_GROUP_OPENIDS` | Alertmanager 通知 |
| `/alert/tano` | `ALERTMANAGER_TANO_GROUP_OPENIDS` | Alertmanager 通知 |

目标：让 Uptime Kuma 通知支持第二条路由 `/uptime-kuma/lanunion`，发往
`TARGET_GROUP_LANUNION_OPENID` 对应的群组。

现状问题：`src/plugins/uptime_kuma/__init__.py` 只硬编码了一条路由，且目标群
直接写死在 handler 里（`config.target_group_openid`），无法承载第二条路由。

## 已确认的决策

| 决策点 | 结论 | 理由 |
|---|---|---|
| 监控面板链接 | 保持硬编码 `https://status.tano.asia/dashboard/{id}` | lanunion 与 tano 共用同一个 Uptime Kuma 实例 |
| 目标群数量 | 每条路由单个 OpenID，不做逗号分隔 | 与 `TARGET_GROUP_OPENID` 既有约定一致 |
| 配置缺失行为 | 必填（`min_length=1`），启动即失败 | 与 `TARGET_GROUP_OPENID` 一致 |
| 实现方案 | 在现有插件内参数化（方案 A） | 复用全部格式化逻辑，与 Alertmanager 插件的双路由写法对齐 |
| 现有 handler 命名 | `handle_uptime_kuma_webhook` 保持不变 | 改成 `handle_tano_...` 会暗示存在 `TARGET_GROUP_TANO_OPENID`，而实际没有 |

## 架构

整体照搬 `src/plugins/alertmanager_webhook/__init__.py` 已有的多路由模式：
一个承载全部逻辑的核心函数，加上每条路由一个薄包装 handler，各自绑定自己的
config 字段。

```
POST /uptime-kuma          → handle_uptime_kuma_webhook
                           → _forward_uptime_kuma_webhook(req, config.target_group_openid)

POST /uptime-kuma/lanunion → handle_lanunion_uptime_kuma_webhook
                           → _forward_uptime_kuma_webhook(req, config.target_group_lanunion_openid)
```

两条路由共用同一套格式化、证书到期解析、状态映射与发送逻辑，不存在重复实现。

`/uptime-kuma` 与 `/uptime-kuma/lanunion` 都是精确路径，在 FastAPI 驱动下不构成
冲突（非路径参数匹配）。

## 实现细节

插件源码只改动 `src/plugins/uptime_kuma/__init__.py` 一个文件；另有测试、
依赖声明与文档的配套改动，见下文。

### 1. Config 新增必填字段

```python
class Config(BaseModel):
    """Plugin settings loaded from the NoneBot environment."""

    target_group_openid: str = Field(min_length=1)
    target_group_lanunion_openid: str = Field(min_length=1)
```

字段缺失时，NoneBot 在加载插件阶段抛出 pydantic `ValidationError`，整个进程启动
失败。已实测确认该行为。

### 2. 抽出核心发送函数

把 `handle_uptime_kuma_webhook` 现有函数体原样搬入
`_forward_uptime_kuma_webhook(request: Request, target_group_openid: str) -> Response`，
唯一变化是两处 `config.target_group_openid` 替换为函数参数。其余逻辑、
日志文案、状态码全部保持不变。

### 3. 两个薄包装 handler

```python
async def handle_uptime_kuma_webhook(request: Request) -> Response:
    """Forward an Uptime Kuma webhook to the configured group."""
    return await _forward_uptime_kuma_webhook(request, config.target_group_openid)


async def handle_lanunion_uptime_kuma_webhook(request: Request) -> Response:
    """Forward a Lanunion Uptime Kuma webhook to its configured group."""
    return await _forward_uptime_kuma_webhook(
        request, config.target_group_lanunion_openid
    )
```

`handle_uptime_kuma_webhook` 的既有 name、docstring、行为均不变。

### 4. 注册第二条路由

```python
get_driver().setup_http_server(
    HTTPServerSetup(
        path=URL("/uptime-kuma/lanunion"),
        method="POST",
        name="uptime-kuma-lanunion-webhook",
        handle_func=handle_lanunion_uptime_kuma_webhook,
    )
)
```

### 不引入的东西

- 不加 `route_name` 参数。`_forward_alertmanager_webhook` 里的 `route_name` 只用于
  "未配置" 的 503 文案，而本插件配置为必填、不存在该分支。
- 不改动 `_uptime_kuma_notification`、证书到期正则、`_status`、
  `_certificate_expiry_status` 等任何格式化逻辑。
- 不把两个 webhook 插件共用的 `_json_response` / `_get_qq_bot` / `_code` /
  `_utc_plus_8` 抽成公共模块。这是既有的重复，但与本次目标无关，属于独立的
  重构议题。

## 错误处理

与现有 `/uptime-kuma` 完全一致，新增路由不引入新的错误分支：

| 情况 | 状态码 | 响应体 |
|---|---|---|
| 请求体为空 | — | **不可达，见下方说明** |
| QQ bot 未连接 | 503 | `{"detail": "QQ bot is not connected"}` |
| Markdown 发送失败且纯文本降级也失败 | 502 | `{"detail": "failed to send QQ group message"}` |
| 成功 | 200 | `{"status": "forwarded"}` |
| 配置缺失 | — | 进程启动阶段抛 pydantic `ValidationError` |

Markdown 发送失败时先降级发送纯文本（截断到 1900 字符），失败才返回 502 —— 这条
既有行为保留。

### `400 webhook body is empty` 是死代码

原设计假设空请求体会命中 `if not message: return _json_response(400, ...)`。**实测
证明该分支永远不会触发**，属于既有代码中已存在的缺陷，与本次改动无关：

`_uptime_kuma_notification` 返回的第二个值是 `plain_text`，它的构造方式是
`f"{plain_prefix}\n\n{message}".strip()`，而 `plain_prefix` 恒为
`"{icon} {monitor_name or 'Uptime Kuma'} · {status}"` 加字段列表。即使 `message`
为空串，表头本身也保证了结果非空：

```
_uptime_kuma_notification(None, b"")
  -> markdown: '**⚪ Uptime Kuma · 未知状态**\n\n```text\n\n```'
  -> plain   : '⚪ Uptime Kuma · 未知状态'      # 非空
```

驱动侧的分析是对的（FastAPI 驱动用 `contextlib.suppress(Exception)` 包裹
`await request.json()`，空 body 时 `json` 为 `None`、`content` 为 `b""`，不会抛
500），错的只是「`_format_webhook_message` 返回空串」到「handler 判定为空」这一步
推论——handler 看的是 `plain_text`，不是那个空串。

**因此空 body 的请求会继续走到 `_get_qq_bot()`**，返回 503（无 bot）或 200/502
（有 bot）。本设计不修改这一行为，因为改动它属于独立议题，会波及
`_uptime_kuma_notification` 的返回值语义。是否需要清理这个死分支，另行决定。

## 测试

### 现状问题（已实测定位）

`tests/test_uptime_kuma.py` 目前**无法运行**，有两个独立原因：

1. 导入 `src.plugins.uptime_kuma` 会触发模块级 `get_plugin_config(Config)`，在没有
   `nonebot.init()` 的环境下抛 `ValueError: NoneBot has not been initialized`。
2. 环境中未安装 pytest（`pyproject.toml` 与 `requirements.txt` 均无声明）。

已实测确认：在 `nonebot.init(driver="~fastapi", target_group_openid=...)` 之后，
插件模块可正常导入，`setup_http_server` 不报错，`MessageSegment.markdown()` 与
`Response.status_code` 均可脱离 bot 实例使用。

### 基础设施修复

- `pyproject.toml` 的 `[project.optional-dependencies].dev` 增加 `pytest` 与
  `pytest-asyncio`。
- `pyproject.toml` 增加 `[tool.pytest.ini_options]`：

  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  pythonpath = ["."]
  ```

  `asyncio_mode = "auto"` 使异步测试函数无需装饰器即可被收集。

  `pythonpath = ["."]` 是必需的，不是可选优化：`src/` 与 `tests/` 下都没有
  `__init__.py`，二者均为命名空间包，测试通过 `from src.plugins.uptime_kuma import ...`
  导入模块。若不加这一项，pytest 默认的 `prepend` 导入模式只会把 `tests/` 目录塞进
  `sys.path`，而不会放入仓库根目录，导致 `pytest tests/` 直接报
  `ModuleNotFoundError: No module named 'src'`（只有 `python -m pytest` 恰好因
  当前工作目录进入 `sys.path` 而侥幸可用）。显式声明后两种调用方式都能正常工作。

- 新增 `tests/conftest.py`，在导入期完成一次初始化，并显式传入两个必填配置：

  ```python
  nonebot.init(
      driver="~fastapi",
      target_group_openid="test-openid",
      target_group_lanunion_openid="test-lanunion-openid",
  )
  ```

  `nonebot.init()` 的关键字参数优先级高于环境变量，因此本机 `.env` 中的真实
  OpenID 不会污染测试。此点已实测：临时写入 `TARGET_GROUP_OPENID=from-dotenv-file`
  的 `.env` 后，kwargs 传入的 `from-init-kwarg` 仍然胜出。

  注意 `get_plugin_config` 内部会再次读取 env_file，因此这一点不是想当然的结论，
  而是必须依赖 kwargs 的最高优先级。

### 新增测试

在 `tests/test_uptime_kuma.py` 中补充路由映射测试，用一个记录调用的 FakeBot
替换 `_get_qq_bot`，断言两条路由各自发往正确的群：

- `handle_uptime_kuma_webhook` → `send_to_group` 收到 `test-openid`
- `handle_lanunion_uptime_kuma_webhook` → `send_to_group` 收到 `test-lanunion-openid`

这两条断言正是本次改动的核心风险点（配置字段与路由的绑定关系），且不依赖任何
真实 QQ 凭据。

## 文档更新

- `.env.example`：在 `TARGET_GROUP_OPENID` 上方补 `# /uptime-kuma` 标注，并新增
  `# /uptime-kuma/lanunion` 与 `TARGET_GROUP_LANUNION_OPENID=replace-with-lanunion-group-openid`。
- `README.md`：
  - "Uptime Kuma Webhook" 章节改为与 "Alertmanager Webhook" 对称的两条路由说明。
  - "QQ Official Bot Webhook" 章节末尾列举同一域名下路径的那句，补上
    `/uptime-kuma/lanunion`。

## 验证方式

静态检查（`ruff` 与 `pyright` 装在系统 Python 3.11 下，可直接调用）：

```bash
ruff check .
ruff format --check .
pyright
```

单元测试（因已声明 `pythonpath = ["."]`，`pytest` 与 `python -m pytest` 均可）：

```bash
.venv/bin/python -m pytest tests/ -q
```

首次运行前需安装新增的开发依赖：

```bash
.venv/bin/python -m pip install pytest pytest-asyncio
```

无需 QQ 凭据的路由冒烟测试。判据是**「不是 404」**：只要响应来自我们的 handler，
就说明路由挂上了。

```bash
for p in /uptime-kuma /uptime-kuma/lanunion /uptime-kuma/unknown; do
  printf '%-26s -> %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8080$p)"
done
```

预期（本地未配置可用 QQ 凭据时）：

| 路径 | 状态码 |
|---|---|
| `/uptime-kuma` | 503 |
| `/uptime-kuma/lanunion` | 503 |
| `/uptime-kuma/unknown` | 404（对照组） |

503 的响应体为 `{"detail": "QQ bot is not connected"}`。若 `.env` 中 QQ 凭据可用，
bot 会成功连接，前两条变为 200 或发送失败时的 502——判据始终是那条对照线。

**不要期待 400**：空 body 不会命中 `webhook body is empty` 分支，该分支不可达，
详见上文。

真正的端到端验证需在 Uptime Kuma 中新建一个 Webhook 通知指向
`https://<host>/uptime-kuma/lanunion`，并确认消息落在 lanunion 群。

## 遗留事项（本次不处理）

- 两个 webhook 插件之间重复的 `_json_response` / `_get_qq_bot` / `_code` /
  `_utc_plus_8` / 发送降级逻辑，可另行抽成公共模块。
- 若 lanunion 日后迁移到独立的 Uptime Kuma 实例，硬编码的
  `status.tano.asia` 面板链接需要改为按路由可配置。
