# Alertmanager Webhook JSON 格式说明

## 概述

Alertmanager 的 `webhook_configs` 会通过 HTTP POST 请求发送标准 JSON
数据。

请求格式：

``` http
POST /alert HTTP/1.1
Content-Type: application/json
```

Webhook 接收端可以根据固定字段解析告警信息。

------------------------------------------------------------------------

## JSON 示例

``` json
{
  "receiver": "webhook",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "NodeDown",
        "severity": "critical",
        "instance": "47.83.216.37:9100",
        "job": "node"
      },
      "annotations": {
        "summary": "节点离线",
        "description": "节点超过2分钟无法访问"
      },
      "startsAt": "2026-08-07T11:00:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "http://prometheus:9090/graph",
      "fingerprint": "abc123"
    }
  ],
  "groupLabels": {
    "alertname": "NodeDown"
  },
  "commonLabels": {
    "alertname": "NodeDown",
    "severity": "critical"
  },
  "commonAnnotations": {
    "summary": "节点离线"
  },
  "externalURL": "http://alertmanager:9093",
  "version": "4",
  "groupKey": "{}:{alertname=\"NodeDown\"}"
}
```

------------------------------------------------------------------------

# 字段说明

## 顶层字段

  字段                说明
  ------------------- ---------------------------------------
  receiver            当前使用的 Alertmanager receiver 名称
  status              当前告警状态，firing 或 resolved
  alerts              告警数组
  groupLabels         用于告警聚合的标签
  commonLabels        所有告警共有标签
  commonAnnotations   所有告警共有注释
  externalURL         Alertmanager 地址
  version             Webhook API 版本
  groupKey            告警分组标识

------------------------------------------------------------------------

# alerts 字段

`alerts` 是一个数组，因为 Alertmanager 会进行告警聚合。

示例：

``` json
"alerts": [
    {},
    {},
    {}
]
```

因此接收程序应该遍历：

``` python
for alert in data["alerts"]:
    handle(alert)
```

不要只读取第一个告警。

------------------------------------------------------------------------

# labels

labels 来自 Prometheus Rule。

例如：

``` yaml
labels:
  severity: critical
```

Webhook：

``` json
{
  "labels": {
    "severity": "critical"
  }
}
```

常用标签：

  标签        说明
  ----------- --------------------
  alertname   告警名称
  severity    告警等级
  instance    实例地址
  job         Prometheus任务名称
  service     服务名称

------------------------------------------------------------------------

# annotations

annotations 用于描述告警。

Prometheus Rule:

``` yaml
annotations:
  summary: "CPU过高"
  description: "CPU超过90%"
```

Webhook:

``` json
{
  "annotations": {
    "summary": "CPU过高",
    "description": "CPU超过90%"
  }
}
```

------------------------------------------------------------------------

# Alertmanager Webhook 配置示例

``` yaml
receivers:

- name: webhook

  webhook_configs:

  - url: "https://example.com/alert/lanunion"

    send_resolved: true

- name: tano-webhook

  webhook_configs:

  - url: "https://example.com/alert/tano"

    send_resolved: true
```

------------------------------------------------------------------------

# 与机器人系统集成

典型架构：

    Prometheus
        |
        v
    Alertmanager
        |
        v
    Webhook
        |
        v
    通知服务
        |
        +-- Telegram
        +-- QQ Bot
        +-- 企业微信
        +-- Email

Webhook 非常适合作为统一通知入口。

------------------------------------------------------------------------

# 安全建议

推荐：

-   使用 HTTPS
-   使用反向代理增加认证
-   不直接暴露内部服务
-   对 webhook 请求进行来源校验

例如：

    Alertmanager
          |
          v
    https://notify.example.com/alert/lanunion

------------------------------------------------------------------------

# 应用场景

适用于：

-   服务器宕机通知
-   CPU/内存/磁盘告警
-   HTTPS证书过期提醒
-   Docker 服务异常
-   运维机器人通知
