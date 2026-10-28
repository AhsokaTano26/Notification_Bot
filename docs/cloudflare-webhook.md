# Cloudflare 通知接入

接口：`POST /webhook/cloudflare`。

## 配置

1. 超级管理员通过 QQ 执行：

   ```text
   /配置 cloudflare add tano replace-with-a-long-random-secret 群一OpenID,群二OpenID
   ```

   名称使用 1-64 个英文字母、数字、下划线或连字符。密钥由你手动创建，要求
   16-256 个非空格可打印 ASCII 字符；使用足够长的随机值并自行保管原文。
   目标群可以有多个，用英文逗号分隔、自动去重；群内也可填 `当前群`。
   建议私聊填写密钥，避免群内原始命令被其他成员看到。
2. 在 Cloudflare Notifications 中新增 Generic webhook，URL 填写
   `https://你的域名/webhook/cloudflare`，Secret 填同一密钥原文。
3. 测试 webhook 并绑定所需告警策略。Bot 必须已加入目标 QQ 群并具备发消息权限。

可以重复添加不同名称、不同密钥，各自指定目标群。数据库只保存密钥的 SHA-256
摘要，查看命令不会返回原文，也不能将同一密钥重复绑定为多个名称。

```text
/配置 cloudflare list
/配置 cloudflare remove tano
```

删除后立即停止接受该密钥的新请求；已经通过验证的在途请求可能完成投递。
修改目标群或轮换密钥时，删除对应名称后重新添加。

## 请求及消息

按照 [Cloudflare 官方 schema](https://developers.cloudflare.com/notifications/reference/webhook-payload-schema/)，
请求头必须包括 `cf-webhook-auth: 你的密钥`。不接受查询参数密钥或 Bearer 令牌。
JSON 示例：

```json
{
  "name": "Origin health check",
  "text": "The origin has become unhealthy.",
  "data": {
    "zone_name": "example.com",
    "new_status": "unhealthy"
  },
  "ts": 1793188800,
  "account_id": "example-account",
  "policy_id": "example-policy",
  "policy_name": "Origin health check",
  "alert_type": "health_check_status_notification",
  "alert_event": "ALERT_STATE_EVENT_START"
}
```

`text` 必须为非空字符串。`data` 若出现必须为 JSON 对象，其内部支持不同告警类型
的嵌套数据。`ts` 若出现必须为能转换为日期的整数 Unix 秒时间戳。
其他已知文本字段出现时必须为字符串；允许省略 Cloudflare 可选字段，以及新增
未知字段。标题优先取 `name`，其次取 `policy_name`，缺失时使用默认标题。

QQ 收到策略名、告警类型、告警状态、UTC+8 时间、正文及详情。开始事件显示
“告警中”，结束事件显示“已恢复”，未知事件保留事件名称。每个目标群收到一条
不超过 1900 字符的纯文本；长正文和详情会截断，不进行外部链接抓取。

## HTTP 响应

| 状态 | 含义 |
| --- | --- |
| 200 | 已发送至全部目标群，响应 `{"status":"forwarded","messages":"2"}` 中的数量为成功投递数 |
| 400 | 密钥有效，但 JSON 格式或字段类型无效 |
| 401 | 未携带 `cf-webhook-auth`、密钥错误、已撤销或尚未配置任何密钥 |
| 502 | QQ 发送失败；继续尝试其他群，响应中给出成功数与总数 |
| 503 | QQ Bot 尚未连接 |

部分群投递失败后，Cloudflare 重试可能使已成功的群再次收到通知；当前接口不做跨
请求去重。数据库和目标群配置在每次请求中读取，无需重启。

部署后验证：先用 Cloudflare 控制台发送测试，确认目标群收到消息；删除对应
密钥后再次测试应返回 401；重新添加密钥后应恢复。所有管理命令及帮助仅超级
管理员可用，普通 QQ 群管理员身份不足以管理 Bot。
