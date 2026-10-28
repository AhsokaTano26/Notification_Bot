# 数据库配置与 Cloudflare 通知

用户要求将目标群和 Kuma Push URL 从环境变量移入容器外持久化的数据库，通过仅超级管理员可用的 QQ 命令配置，并接入需要手动创建、支持多个密钥的 Cloudflare webhook。

## 实现选择

使用 Python 标准库 SQLite，数据库路径固定为 `data/notification_bot.sqlite3`。两个 Compose 配置均绑定 `./data:/app/data`。与独立 PostgreSQL 相比，这符合现有单进程小型 Bot 部署，无需新增数据库服务、凭据或 Python 依赖。数据库文件及其日志不得进入 Git 或 Docker 构建上下文。

环境保留 QQ 凭据、QQ 事件接收选项、驱动与首次启动的 `SUPERUSERS`。目标群及 `KUMA_PUSH_URL` 不再读取旧环境配置，也不隐式导入；由管理员通过命令填写。群配置每次请求从数据库读取；Kuma 任务每 60 秒读取最新 URL，空值跳过检查，无需重启即可启停。

## 数据与权限

`settings` 保存六项受白名单限制的运行配置。`superusers` 保存 QQ 用户 OpenID；初始化时仅一次从 NoneBot `SUPERUSERS` 导入。支持管理员增删，禁止删除最后一位。QQ 群管理员身份不赋予配置权限。所有配置和帮助命令同时在 matcher 和处理逻辑检查数据库权限。

`cloudflare_keys` 保存命名密钥的 SHA-256 摘要及目标群列表。管理员手动指定密钥（16-256 个非空格可打印 ASCII 字符），按名称创建、列出、删除；不回显原始密钥或 Kuma URL 中的令牌。每个密钥绑定一个或多个群，相同原始密钥不得重复添加。删除后新的请求立即失效，已通过验证的在途请求可能完成投递。

QQ 提供 `/配置 help|list|set|unset`、`/配置 admin list|add|remove`、`/配置 cloudflare list|add|remove`，并提供 `/help`、`/帮助`。设置名与原环境变量名一致；群设置接受 `当前群`，自动取得 `group_openid`。命令采用单条填写形式，避免多轮会话状态及群内误操作。支持群消息与 C2C 消息。

## Webhook

保留现有五条通知路由。未配置目标群返回 503，Bot 仍可正常启动并接收配置命令。

新增 `POST /webhook/cloudflare`，验证官方 `cf-webhook-auth` 请求头，缺失或无匹配密钥返回 401，随后验证 JSON。将策略名称、告警类型、事件状态、UTC+8 时间、正文和告警特定数据转换为不超过 1900 字符的 QQ 文本，转发至匹配密钥的所有群。部分投递失败返回 502，Bot 未连接返回 503。新版本字段允许出现，官方可选字段不作为必填项。请求中的密钥、正文验证异常不得被回显或记录。

参考：https://developers.cloudflare.com/notifications/reference/webhook-payload-schema/

## 验证范围

使用临时 SQLite 和无凭据 QQ 替身验证持久化、一次性引导、管理员授权及删除保护、动态路由、多群去重、Kuma 动态启停、Cloudflare 多密钥与撤销、错误鉴权及格式、QQ 失败响应。运行完整 pytest、Ruff 检查与格式检查、Pyright，并检查 Compose 配置与实际 NoneBot 插件加载。真实 QQ 投递及 Cloudflare 控制台测试由部署后执行。
