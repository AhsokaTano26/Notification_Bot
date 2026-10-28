# Notification_Bot

## How to start

1. generate project using `nb create` .
2. create your plugin using `nb plugin create` .
3. writing your plugins under `src/plugins` folder.
4. run your bot using `nb run --reload` .

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

Send a JSON notification to `POST https://<your-host>/webhook/general`. Set
`GENERAL_WEBHOOK_GROUP_OPENID` to the destination group's OpenID (available via
`/群信息` in that group). The endpoint sends one QQ group message per request.
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
Uptime Kuma **Push** monitor. Copy that monitor's Push URL to the environment:

```dotenv
KUMA_PUSH_URL=https://kuma.example.com/api/push/your-monitor-token
QQ_USE_WEBSOCKET=true
DRIVER=~fastapi+~httpx+~websockets
```

The WebSocket client dependency is included in the project's requirements.
The default HTTP Webhook configuration above does not provide a WebSocket
session and therefore reports `down` under this check. Leave `KUMA_PUSH_URL`
empty to disable health reporting.

Checks run immediately at startup and then every 60 seconds. Every configured
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

Each variable accepts one or more group OpenIDs separated by commas. Every
object in the `alerts` array becomes a separate QQ message in every configured
target group. The message includes the alert name, status, severity, instance,
job, service, summary, description, and timestamps. It does not include a
Prometheus or other external link.

The QQ Bot is initialized when the service starts, so Alertmanager and Uptime
Kuma can send alerts before any QQ message arrives. Displayed webhook timestamps
are converted from UTC to UTC+8.

## QQ Official Bot Webhook

This project receives QQ events through HTTP Webhook, not a gateway WebSocket.
In the QQ Developer Platform, set the callback URL to
`https://<your-host>/qq/webhook` and complete its verification request. Keep
`QQ_USE_WEBSOCKET=false` and `QQ_VERIFY_WEBHOOK=true` in `.env`; the adapter
uses `QQ_SECRET` to verify signed events. The same domain receives every path:
`/qq/webhook` for QQ, `/uptime-kuma` and `/uptime-kuma/lanunion` for Uptime
Kuma, `/alert/lanunion` and `/alert/tano` for Alertmanager, and
`/webhook/general` for general notifications.

## Docker Deployment

1. Create `.env` from `.env.example` and fill in all QQ and webhook settings.
   The container reads this file at runtime; it is deliberately excluded from
   the image. Keep `DRIVER=~fastapi+~httpx`: the QQ adapter needs
   the HTTP client driver to request access tokens.
2. Build and start the service:

   ```bash
   docker compose up -d --build
   ```

3. Inspect the service with `docker compose logs -f notification-bot`.

The application listens on port `8080`; map it behind an HTTPS reverse proxy
before exposing `/qq/webhook` or any notification webhook path to the
internet. Stop it with
`docker compose down`. For a non-container installation, use
`pip install -r requirements.txt` and start with `python bot.py`.
