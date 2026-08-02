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
   `QQ_C2C_GROUP_AT_MESSAGES=true`; it is required for group command events.
   In the destination QQ group, send `/群信息` and use the returned **群 OpenID** as
   `TARGET_GROUP_OPENID`; this is not the visible QQ group number.
2. In Uptime Kuma, create a Webhook notification pointing to
   `POST https://<your-host>/uptime-kuma`.

The webhook forwards `msg` or `message` from a JSON body; other JSON payloads
are formatted and sent as-is. Use `/我的ID` to retrieve your QQ OpenAPI user
OpenID. The bot must be invited to the target group and granted the QQ Official
Bot permissions needed to receive group messages and send group messages. The
Uptime Kuma endpoint does not require a token, so restrict public access to it
at the reverse proxy or platform firewall when possible.

## QQ Official Bot Webhook

This project receives QQ events through HTTP Webhook, not a gateway WebSocket.
In the QQ Developer Platform, set the callback URL to
`https://<your-host>/qq/webhook` and complete its verification request. Keep
`QQ_USE_WEBSOCKET=false` and `QQ_VERIFY_WEBHOOK=true` in `.env`; the adapter
uses `QQ_SECRET` to verify signed events. The same domain receives both paths:
`/qq/webhook` for QQ and `/uptime-kuma` for Uptime Kuma.

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
before exposing `/qq/webhook` and `/uptime-kuma` to the internet. Stop it with
`docker compose down`. For a non-container installation, use
`pip install -r requirements.txt` and start with `python bot.py`.
