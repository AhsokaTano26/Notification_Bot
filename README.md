# Notification_Bot

## How to start

1. generate project using `nb create` .
2. create your plugin using `nb plugin create` .
3. writing your plugins under `src/plugins` folder.
4. run your bot using `nb run --reload` .

## Documentation

See [Docs](https://nonebot.dev/)

## Uptime Kuma Webhook

1. Copy `.env.example` to `.env` and fill in the QQ Official Bot credentials:
   `QQ_APP_ID`, `QQ_TOKEN`, and `QQ_SECRET`. Keep
   `QQ_C2C_GROUP_AT_MESSAGES=true`; it is required for group @ commands. In
   the destination QQ group, send
   `@机器人 /群信息` and use the returned **群 OpenID** as
   `TARGET_GROUP_OPENID`; this is not the visible QQ group number.
2. Set `UPTIME_KUMA_WEBHOOK_TOKEN` to a long random secret.
3. In Uptime Kuma, create a Webhook notification pointing to
   `POST https://<your-host>/uptime-kuma`. Set either
   `Authorization: Bearer <token>` or `X-Webhook-Token: <token>`.

The webhook forwards `msg` or `message` from a JSON body; other JSON payloads
are formatted and sent as-is. Use `@机器人 /我的ID` to retrieve your QQ OpenAPI
user OpenID. The bot must be invited to the target group and granted the QQ
Official Bot permissions needed to receive @ messages and send group messages.

## Docker Deployment

1. Create `.env` from `.env.example` and fill in all QQ and webhook settings.
   The container reads this file at runtime; it is deliberately excluded from
   the image. Keep `DRIVER=~fastapi+~httpx+~websockets`: the QQ adapter needs
   the HTTP client driver to request access tokens.
2. Build and start the service:

   ```bash
   docker compose up -d --build
   ```

3. Inspect the service with `docker compose logs -f notification-bot`.

The application listens on port `8080`; map it behind an HTTPS reverse proxy
before exposing `/uptime-kuma` to the internet. Stop it with
`docker compose down`. For a non-container installation, use
`pip install -r requirements.txt` and start with `python bot.py`.
