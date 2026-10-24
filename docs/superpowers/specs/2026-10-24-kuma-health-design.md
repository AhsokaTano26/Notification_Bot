# Kuma health

Add the `kuma_health` NoneBot plugin. `KUMA_PUSH_URL` is the existing Kuma
Push monitor URL for this deployment; an empty value disables the plugin.
Check immediately after startup and every 60 seconds thereafter.

Only report `up` when every configured QQ bot is registered, uses WebSocket,
has received READY, and its live `me()` identity request succeeds. Missing
bots, Webhook mode, unready sessions, errors and timeouts report `down` with
a short diagnostic. Recheck registration and readiness after the API call.

Use a native asyncio background task with startup/shutdown hooks and the
existing HTTPX dependency. A scheduler plugin would add an unnecessary
dependency for one periodic job. This is an implementation choice.

Give the complete QQ check and the Push request 10-second limits each.
Merge `status`, `msg` and `ping` into the supplied URL, replacing stale
values and retaining unrelated query parameters. Validate Kuma's HTTP status
and `ok` response; log only the failure type if delivery fails, then retry
on the next cycle. Never log the token-bearing URL. Cancel and await the
task on shutdown. Tests use synthetic credentials and mocked network I/O.
