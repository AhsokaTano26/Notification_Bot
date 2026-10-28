# Notification_Bot

## 快速启动

复制 `.env.example` 为 `.env`，填写 QQ 凭据和初始 `SUPERUSERS`，然后运行
`docker compose -f compose.yaml up -d --build`。通知目标群、Kuma Push URL 和
Cloudflare 密钥都保存在挂载的 SQLite 数据库中，通过 QQ 的 `/配置` 命令管理。
超级管理员发送 `/help` 查看帮助。

## Documentation

See [Docs](https://nonebot.dev/)

## Dependencies and Development

Python 3.10+ is required. The runtime requirements in `pyproject.toml` and
`requirements.txt` are kept in sync. The October 2026 update uses
[NoneBot 2.5.0](https://pypi.org/project/nonebot2/),
[QQ adapter 1.7.3](https://pypi.org/project/nonebot-adapter-qq/), and
[python-dotenv 1.2.4](https://pypi.org/project/python-dotenv/), with direct
dependencies on HTTPX 0.28.1, Pydantic 2.14.1 and yarl 1.25.1. Version ranges
allow compatible updates while excluding the next breaking release line.

All application plugins are maintained locally in `src/plugins`; no external
NoneBot plugin packages are currently registered. The development extra includes
NB CLI, Ruff, Pyright, pytest and pytest-asyncio. Install or update the local
development environment with [uv](https://docs.astral.sh/uv/):

```bash
uv venv  # First-time setup only; use any supported Python 3.10+ interpreter.
uv pip install --upgrade -r pyproject.toml --extra dev
source .venv/bin/activate
pytest
ruff check .
ruff format --check .
pyright
```

These checks run without sending real QQ messages or Kuma pushes. Runtime-only
installations can continue using `pip install --upgrade -r requirements.txt`.

## 数据库与 QQ 配置管理

数据库固定为容器内 `/app/data/notification_bot.sqlite3`，两个 Compose 文件都将
宿主机 `./data` 绑定挂载到 `/app/data`，重建或删除容器不会删除配置。本地直接运行
时使用当前工作目录下的 `data/notification_bot.sqlite3`。数据库会自动创建，
不需要另外运行数据库服务，也不需要设置数据库环境变量。

`.env` 仅负责 QQ 凭据、QQ 连接与事件选项、首次管理员引导，以及基础 `DRIVER`
设置。下表配置不再读取同名环境变量，也不会自动导入旧值；升级后请通过 QQ 重新
填写。未设置目标群时 Bot 仍会启动，对应通知接口返回 503。

| 数据库配置项 | 通知接口 / 用途 | 值 |
| --- | --- | --- |
| `TARGET_GROUP_OPENID` | `/uptime-kuma` | 单个群 OpenID |
| `TARGET_GROUP_LANUNION_OPENID` | `/uptime-kuma/lanunion` | 单个群 OpenID |
| `ALERTMANAGER_LANUNION_GROUP_OPENIDS` | `/alert/lanunion` | 一个或多个群，英文逗号分隔 |
| `ALERTMANAGER_TANO_GROUP_OPENIDS` | `/alert/tano` | 一个或多个群，英文逗号分隔 |
| `GENERAL_WEBHOOK_GROUP_OPENID` | `/webhook/general` | 单个群 OpenID |
| `KUMA_PUSH_URL` | 现有 Kuma Push 监控 | HTTP(S) URL；清空禁用 |

初始超级管理员使用 **QQ OpenAPI 用户 OpenID，不是 QQ 号**：

1. 不知道用户 OpenID 时，先设置 `SUPERUSERS=[]` 启动 Bot，在群聊或私聊发送
   `/我的ID`（别名 `/whoami`）取得自己的标识。
2. 在 `.env` 填写 `SUPERUSERS=["qq:你的用户OpenID"]`，重新创建容器
   `docker compose -f compose.yaml up -d`。支持填写多个初始管理员。
3. 首次非空管理员列表会写入数据库。此后管理员以数据库为准，修改环境变量或
   重启不会重新添加已撤销的管理员。若此前未填写任何管理员，仍可补填后重启引导。

群聊和私聊中的用户 OpenID 若不同，请分别通过 `/我的ID` 查询，并将需要使用的
标识都加入超级管理员。QQ 群主或群管理员身份本身不授予配置权限。
`/我的ID` 只返回调用者自己的标识，`/群信息` 返回当前群 OpenID；这两个查询
可供普通用户使用。下面所有管理命令和帮助均仅数据库超级管理员可用：

```text
/help
/配置 help
/配置 list
/配置 set TARGET_GROUP_OPENID 当前群
/配置 set TARGET_GROUP_LANUNION_OPENID 群OpenID
/配置 set ALERTMANAGER_LANUNION_GROUP_OPENIDS 群一OpenID,群二OpenID
/配置 set ALERTMANAGER_TANO_GROUP_OPENIDS 群OpenID
/配置 set GENERAL_WEBHOOK_GROUP_OPENID 当前群
/配置 set KUMA_PUSH_URL https://kuma.example.com/api/push/your-monitor-token
/配置 unset KUMA_PUSH_URL
/配置 admin list
/配置 admin add 用户OpenID
/配置 admin remove 用户OpenID
/配置 cloudflare list
/配置 cloudflare add tano 你手动创建的密钥 群OpenID
/配置 cloudflare remove tano
```

`/配置` 的别名为 `/bot-config`；`/help` 的别名为 `/帮助`。群设置和 Cloudflare
目标群支持 `当前群`，私聊请填写具体 OpenID。配置名不区分大小写；含空格的参数
需用英文引号包裹。删除最后一位超级管理员会被拒绝。

配置保存后无需重启，路由在下次请求时读取新值，Kuma 检查最迟 60 秒生效。
`/配置 unset 配置项` 清空目标或禁用 Push。查看配置只显示 Push URL 是否已设置，
不会回显完整 URL；Cloudflare 密钥只存储 SHA-256 摘要，无法取回原文。
建议在私聊中填写密钥和 Push URL，因为群成员可看到你发送的原始消息。
管理命令内容会在应用日志中隐藏。

备份时先停止 Bot，再复制整个宿主机 `data/` 目录，完成后启动；恢复时在 Bot
停止期间还原该目录。保管好目录与备份，其中包含目标群、管理员和 Kuma Push URL。

## Uptime Kuma Webhook

Uptime Kuma sends its Webhook notification payload to one of two routes:

- `POST https://<your-host>/uptime-kuma` uses `TARGET_GROUP_OPENID`.
- `POST https://<your-host>/uptime-kuma/lanunion` uses
  `TARGET_GROUP_LANUNION_OPENID`.

Each database setting holds a single group OpenID; they are not comma-separated.
An unset target disables only its route, which returns HTTP 503.

1. Copy `.env.example` to `.env` and fill in the QQ Official Bot credentials:
   `QQ_APP_ID`, `QQ_TOKEN`, and `QQ_SECRET`. Keep
   `QQ_C2C_GROUP_AT_MESSAGES=true`; it is required for group command events.
   In each destination QQ group, send `/群信息` and use the returned **群 OpenID**
   with `/配置 set TARGET_GROUP_OPENID 群OpenID` or
   `/配置 set TARGET_GROUP_LANUNION_OPENID 群OpenID`; this is not the visible QQ
   group number. Administrators can use `当前群` instead of copying the ID.
2. In Uptime Kuma, create a Webhook notification pointing to the route whose
   group should receive it, for example `POST https://<your-host>/uptime-kuma/lanunion`.

For Uptime Kuma's default JSON body, the Bot formats `monitor` and `heartbeat`
fields into monitor name, type, address, ID, status, latency, and timestamp;
`msg` is retained as the alert detail. Other JSON payloads are sent as-is. Use
`/我的ID` to retrieve your QQ OpenAPI user OpenID. The bot must be invited to the
target group and granted the QQ Official Bot permissions needed to receive group
messages and send group messages. The Uptime Kuma endpoint does not require a
token, so restrict public access to it at the reverse proxy or platform firewall
when possible.

Certificate-expiry messages in Uptime Kuma's default form are parsed even when
they contain no `heartbeat` data. They show the monitored address, certificate
domain, and remaining days: 30 days or fewer is a yellow warning, and 7 days or
fewer is a red urgent alert.

## General Webhook

Send a JSON notification to `POST https://<your-host>/webhook/general`. An
administrator sets the destination with
`/配置 set GENERAL_WEBHOOK_GROUP_OPENID 群OpenID` (available via `/群信息` in that
group). The endpoint sends one QQ group message per request.
See the [complete JSON definition](docs/general-webhook-json.md) for the schema,
field constraints, formatting, examples, and responses.

```json
{
  "title": "部署通知",
  "message": "服务已更新",
  "level": "success"
}
```

## 阅后即焚

`burn_after_reading` 插件默认关闭，开关按 Bot、QQ 群和用户分别生效。
在群内 @Bot 发送以下命令（也支持 `/阅后即焚` 和 `/关闭阅后即焚`）：

- `阅后即焚`：只为发送命令的用户开启，Bot 会在该用户的消息发送 **10 秒后**
  自动撤回，包括这条开启命令。Bot 的确认回复和 Webhook 通知会保留。
- `关闭阅后即焚`：只关闭发送命令用户在当前群的自动撤回，并取消其尚未执行的
  撤回任务；不会改变其他用户的开关或撤回任务。

计时以 QQ 消息的发送时间为准，不依赖已读回执；收到延迟投递的消息会扣除已过去
的时间。开启前已收到的消息、未开启用户的消息以及 Bot 自己的消息不受影响。
开关与待执行任务保存在内存中，Bot 重启后恢复默认关闭状态。
Bot 需要具备撤回群成员消息的权限，并在 QQ 群内获准接收全量消息，才能覆盖
该用户的普通发言；只接收 @ 消息时，仅能处理已收到的消息。
根据 [QQ 官方撤回接口文档](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_messages_message_id.delete.html)，
即使 Bot 已是群管理员，也只能撤回普通群成员的消息，无法撤回群主或管理员消息。
群主和管理员发送开启命令时会收到限制提示，不会开启；请用普通成员账号验证。
QQ 撤回接口失败时，警告日志会包含 HTTP 状态、QQ `code`、`message` 和 `trace_id`，
便于区分参数无效（`40061001`）、无权限（`40062003`）和超时（`40064004`）。
权限和实际撤回效果需在真实 QQ 群内验证。

手动验证：用户 A 发送 `阅后即焚`，再发一条普通消息，两条用户消息应在各自发送
约 10 秒后被撤回；Bot 提示、Webhook 通知和未开启的用户 B 的消息应保留。
A 再发一条消息，并在 10 秒内发送 `关闭阅后即焚`，这条消息应保留；若 B 也已
开启，A 关闭不应影响 B。A 在其他未开启此功能的群内发言也应保留。

## Kuma Health Push

The `kuma_health` plugin reports this deployment's live QQ status to an existing
Uptime Kuma **Push** monitor. An administrator saves its Push URL with
`/配置 set KUMA_PUSH_URL https://kuma.example.com/api/push/your-monitor-token`.
Enable the WebSocket driver in `.env`:

```dotenv
QQ_USE_WEBSOCKET=true
DRIVER=~fastapi+~httpx+~websockets
```

The WebSocket client dependency is included in the project's requirements.
The default HTTP Webhook configuration above does not provide a WebSocket
session and therefore reports `down` under this check. Use
`/配置 unset KUMA_PUSH_URL` to disable health reporting.

The loop starts immediately and reads the current database URL every 60 seconds.
An empty URL skips the probe and push; configuring one at runtime enables reporting
on the next cycle. Every configured
QQ bot must be registered, have a ready WebSocket session, and successfully
complete a fresh QQ `me()` identity request before the plugin pushes `up`.
Disconnected or unready bots, disabled WebSockets, identity errors and
10-second probe timeouts push `down` with a diagnostic message. A bot that
recovers can report `up` on the next check.

The plugin updates `status`, `msg` and measured `ping` using the
[Kuma Push API](https://github.com/louislam/uptime-kuma/wiki/Internal-API), so
URLs copied with existing query parameters also work. Push failures are logged
without exposing the URL's token and retried on the next cycle. Shutdown
cancels the background task and closes its HTTP client. If this process stops
or cannot reach Kuma, Kuma detects the missing heartbeats using the existing
monitor's interval; allow some margin beyond the 60-second reporting period.

## Alertmanager Webhook

Alertmanager sends its standard JSON payload to one of two routes:

- `POST https://<your-host>/alert/lanunion` uses
  `ALERTMANAGER_LANUNION_GROUP_OPENIDS`.
- `POST https://<your-host>/alert/tano` uses
  `ALERTMANAGER_TANO_GROUP_OPENIDS`.

Each database setting accepts one or more group OpenIDs separated by commas. Set
it with `/配置 set ALERTMANAGER_LANUNION_GROUP_OPENIDS 群OpenID` or
`/配置 set ALERTMANAGER_TANO_GROUP_OPENIDS 群OpenID`. Every
object in the `alerts` array becomes a separate QQ message in every configured
target group. The message includes the alert name, status, severity, instance,
job, service, summary, description, and timestamps. It does not include a
Prometheus or other external link.

The QQ Bot is initialized when the service starts, so Alertmanager and Uptime
Kuma can send alerts before any QQ message arrives. Displayed webhook timestamps
are converted from UTC to UTC+8.

## Cloudflare Webhook

新增接口为 `POST https://<your-host>/webhook/cloudflare`，按
[Cloudflare 官方通知 schema](https://developers.cloudflare.com/notifications/reference/webhook-payload-schema/)
解析消息。每个手动创建的密钥绑定一个或多个目标群，互不影响，可随时撤销。

超级管理员先发送：

```text
/配置 cloudflare add tano replace-with-a-long-random-secret 群一OpenID,群二OpenID
```

然后在 Cloudflare Notifications 的 webhook 设置中填写该 URL，将 **Secret**
设为同一原始密钥，选择 Generic webhook，再将 webhook 绑定到通知策略。
Cloudflare 会在 `cf-webhook-auth` 请求头携带 Secret，本接口不使用 URL 查询参数
或 `Authorization` 头鉴权。密钥须为 16-256 个非空格可打印 ASCII 字符，名称须为
1-64 个英文字母、数字、下划线或连字符，不会自动生成。

`/配置 cloudflare list` 查看名称及目标群；
`/配置 cloudflare remove tano` 立即撤销该密钥。修改绑定时先删除再重新添加。
详细 payload、测试方法和 HTTP 响应见 [Cloudflare 接入说明](docs/cloudflare-webhook.md)。

## QQ Official Bot Webhook

This project receives QQ events through HTTP Webhook, not a gateway WebSocket.
In the QQ Developer Platform, set the callback URL to
`https://<your-host>/qq/webhook` and complete its verification request. Keep
`QQ_USE_WEBSOCKET=false` and `QQ_VERIFY_WEBHOOK=true` in `.env`; the adapter
uses `QQ_SECRET` to verify signed events. The same domain receives every path:
`/qq/webhook` for QQ, `/uptime-kuma` and `/uptime-kuma/lanunion` for Uptime
Kuma, `/alert/lanunion` and `/alert/tano` for Alertmanager, and
`/webhook/general` for general notifications, and `/webhook/cloudflare` for Cloudflare.

## Docker Deployment

1. Create `.env` from `.env.example` and fill in QQ credentials and initial superusers.
   The container reads this file at runtime; it is deliberately excluded from
   the image. Keep `DRIVER=~fastapi+~httpx`: the QQ adapter needs
   the HTTP client driver to request access tokens.
2. Build and start the service:

   ```bash
   docker compose -f compose.yaml up -d --build
   ```

3. Inspect the service with `docker compose -f compose.yaml logs -f notification-bot`,
   then fill in notification configuration through QQ.

The bind mount `./data:/app/data` stores SQLite on the host. The alternative
`docker-compose.yml` also includes this mount, uses `.env.prod`, and names the
service `nonebot`; select it explicitly with `-f docker-compose.yml`.

The application listens on port `8080`; map it behind an HTTPS reverse proxy
before exposing `/qq/webhook` or any notification webhook path to the
internet. Stop it with
`docker compose -f compose.yaml down`. For a non-container installation, use
`pip install -r requirements.txt` and start with `python bot.py`.
