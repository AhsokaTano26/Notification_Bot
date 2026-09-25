# 通用 Webhook JSON 协议

## 接口与目标群

- 请求：`POST /webhook/general`
- 请求头：`Content-Type: application/json`
- 目标群：环境变量 `GENERAL_WEBHOOK_GROUP_OPENID`，填写 QQ 官方机器人使用的**群 OpenID**，不是普通群号。可在目标群发送 `/群信息` 获取。
- 每个有效且发送成功的请求只向该群发送一条纯文本 QQ 消息。服务未配置目标群或 QQ 机器人未连接时返回 HTTP 503。

## 请求体定义

请求体必须是 JSON 对象。下面的 JSON Schema 定义字段、类型和允许值；接口还会执行后文列出的时间、链接及最终消息长度校验。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Generic QQ Webhook Request",
  "type": "object",
  "additionalProperties": false,
  "required": ["message"],
  "properties": {
    "message": {
      "type": "string",
      "pattern": "\\S",
      "maxLength": 1900
    },
    "title": {
      "type": ["string", "null"]
    },
    "source": {
      "type": ["string", "null"]
    },
    "level": {
      "enum": ["info", "success", "warning", "error", null]
    },
    "timestamp": {
      "type": ["string", "null"],
      "format": "date-time"
    },
    "fields": {
      "type": ["object", "null"],
      "propertyNames": {
        "pattern": "\\S"
      },
      "additionalProperties": {
        "type": ["string", "number", "boolean"]
      }
    },
    "url": {
      "type": ["string", "null"],
      "format": "uri",
      "pattern": "^https?://"
    }
  }
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `message` | 是 | 非空文本。首尾空白会被去除；仅含空白会返回 400。保留正文内部换行。 |
| `title` | 否 | 标题文本。首尾空白会被去除；空字符串或 `null` 视为未提供。 |
| `source` | 否 | 消息来源，例如 `CI/CD`、`监控平台`。首尾空白会被去除；空字符串或 `null` 不显示。 |
| `level` | 否 | 只能是 `info`、`success`、`warning`、`error`；`null` 或省略表示不显示级别。 |
| `timestamp` | 否 | 带时区的 ISO 8601 时间，例如 `2026-09-26T12:00:00Z` 或 `2026-09-26T20:00:00+08:00`。无时区或无法解析会返回 400；`null` 或省略不显示。 |
| `fields` | 否 | 扁平 JSON 对象。键不能只含空白；值只能是文本、数字或布尔值，不能是对象、数组或 `null`。`null` 或省略表示无附加字段。 |
| `url` | 否 | 带主机名的 HTTP(S) 链接。空字符串或其他协议会返回 400；`null` 或省略不显示。 |

除这些字段外，出现其他顶层字段会返回 HTTP 400，避免拼写错误造成信息被静默丢弃。`title`、`source`、`url`、`timestamp` 和 `fields` 都可以省略。最终排版后的 QQ 消息不得超过 **1900 个字符**；这个跨字段长度限制无法仅靠 JSON Schema 表达，超出时接口返回 HTTP 400，不会截断消息。

## QQ 消息排版

排版顺序为：标题或级别、来源、时间、`fields` 中的各项、空行、正文、链接。只有标题和正文时，两者直接分两行；只有正文时发送去除首尾空白后的正文。级别与默认标题对应如下：

| `level` | 前缀 | 无 `title` 时的标题 |
| --- | --- | --- |
| `info` | 🔵 | 通知 |
| `success` | 🟢 | 成功 |
| `warning` | 🟡 | 警告 |
| `error` | 🔴 | 错误 |

`timestamp` 会转换为 UTC+8，显示为 `YYYY-MM-DD HH:MM:SS+08:00`。`fields` 按请求中的顺序逐行显示为 `键：值`，布尔值显示为 `true` 或 `false`。

### 完整请求示例

```json
{
  "title": "部署失败",
  "message": "构建失败，请检查日志",
  "source": "CI/CD",
  "level": "error",
  "timestamp": "2026-09-26T12:00:00Z",
  "fields": {
    "环境": "production",
    "重试次数": 0,
    "需回滚": true
  },
  "url": "https://example.com/build/42"
}
```

对应的 QQ 消息：

```text
🔴 部署失败
来源：CI/CD
时间：2026-09-26 20:00:00+08:00
环境：production
重试次数：0
需回滚：true

构建失败，请检查日志
链接：https://example.com/build/42
```

最简请求仍然有效：

```json
{"message": "服务已更新"}
```

## 调用与响应

```bash
curl -X POST 'https://<your-host>/webhook/general' \
  -H 'Content-Type: application/json' \
  -d '{"title":"部署通知","message":"服务已更新","level":"success"}'
```

成功发送时返回 HTTP 200：

```json
{"status": "forwarded"}
```

失败时返回 `{"detail": "..."}`：

| HTTP 状态码 | 含义 |
| --- | --- |
| 400 | 请求体不是符合协议的 JSON 对象，或排版后超过 1900 字符。 |
| 502 | QQ 发送失败。 |
| 503 | `GENERAL_WEBHOOK_GROUP_OPENID` 未配置，或 QQ 机器人未连接。 |

此接口自身不校验调用者身份。若对公网开放，请在反向代理或平台防火墙限制访问。
