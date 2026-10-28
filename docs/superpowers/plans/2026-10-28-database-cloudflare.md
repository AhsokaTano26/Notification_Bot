# Database Configuration and Cloudflare Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task, with test-driven development and final code review.

**Goal:** Persist live bot configuration and administrator-managed Cloudflare routes outside the container.

**Architecture:** SQLite via standard-library `sqlite3`, running database operations in `asyncio.to_thread`. A runtime configuration plugin owns initialization and administrator commands; existing webhooks and health checks read its store dynamically.

**Tech Stack:** Python 3.10+, NoneBot 2, QQ adapter, SQLite, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-database-cloudflare-design.md`

## Global Constraints

- Keep QQ credentials, initial superusers, adapter and driver configuration in environment only.
- No runtime setting fallback to environment; no secrets in Git, Docker build context or replies.
- Restrict configuration and help to database superusers; forbid removing the final administrator.
- Preserve existing webhook URLs; bind host `./data` to `/app/data` in both Compose files.
- Keep dependencies unchanged and use annotated, plugin-local helper modules.

## Review Focus

- Restart must not reintroduce removed administrators or overwrite database settings.
- Unauthorized QQ messages must not disclose help, settings, key names or secret values.
- Header authentication must precede payload validation; revoked keys must stop working immediately.
- Empty settings must allow startup; changed routing and Kuma URLs must take effect without restart.
- Invalid commands or database concurrency must not leave partial configuration writes.

### Task 1: Persistent store and administration

**Files:** create `src/plugins/runtime_config/{__init__,database,commands,logging}.py`, `tests/test_runtime_config.py`, `tests/test_admin_commands.py`; update `tests/conftest.py`.

**Interfaces:** `store: SettingsStore`; async `initialize(superusers)`, `get_setting(key)`, `set_setting(key,value)`, `all_settings()`, `is_superuser(id)`, administrator list/add/remove, and Cloudflare key add/list/remove/authenticate operations.

- [x] Add tests for persistence, bootstrap-once, normalization, validation, final-admin protection and hashed key authentication; observe failure.
- [x] Implement SQLite schema and atomic transactions, using one connection per operation in a worker thread.
- [x] Add command authorization, help, configuration and key management tests; observe failure.
- [x] Implement matcher permissions and command processing with no secret echo.
- [x] Verify the store and command tests pass.

### Task 2: Existing runtime consumers

**Files:** modify Uptime Kuma, Alertmanager, generic webhook and Kuma health plugins and their tests; delete obsolete Kuma environment config model.

**Interfaces:** consume `runtime_config.store.get_setting`; retain public handler APIs.

- [x] Add dynamic routing and unset route tests; adapt fixtures to isolated temporary SQLite.
- [x] Verify tests fail before changing consumers.
- [x] Replace environment models with database reads; return 503 for unset targets.
- [x] Start one idle-capable health loop and re-read Push URL each cycle, retaining cancellation behavior.
- [x] Verify existing and new consumer tests pass.

### Task 3: Cloudflare endpoint

**Files:** create `src/plugins/cloudflare_webhook/{__init__,payload}.py`, `tests/test_cloudflare_webhook.py`.

**Interfaces:** `POST /webhook/cloudflare` authenticates via `cf-webhook-auth`, uses per-key target groups, validates payload, and returns 200/400/401/502/503.

- [x] Add HTTP tests with real temporary store for multi-key routing, authentication, revocation, malformed payload, message bounds, disconnected Bot and partial failure; observe failure.
- [x] Implement payload validation, formatting and endpoint registration.
- [x] Verify Cloudflare tests and complete suite.

### Task 4: Deployment and delivery

**Files:** update `.env.example`, `.gitignore`, `.dockerignore`, both Compose files, README; add Cloudflare setup documentation and bootstrap identity command if needed.

- [x] Bind persistent directory and remove runtime settings from example environment.
- [x] Document first-time administrator setup, QQ commands, re-entry of existing values, backup and Cloudflare configuration.
- [x] Run pytest, Ruff lint/format, Pyright, Compose validation and plugin-load smoke check.
- [x] Request fresh code review; resolve material findings and rerun affected checks.

## Execution notes

- Baseline: 70 tests pass; installed runtime/development dependencies satisfy `pip check`.
- Work stays in the user-provided workspace; preserve existing untracked `.DS_Store` files. Do not commit or deploy without a request.
- Completed all four tasks. The database implementation is named `database.py` to avoid a Python package attribute collision with the shared `store` instance.
- Startup operations wait for a readiness event set only after schema/bootstrap commit, so the health task cannot query a missing table.
- Final independent review found a management-log disclosure for tab-separated and unseparated commands. Fixed it and verified all eight real NoneBot command/event combinations; reviewer confirmed resolution.
- Validation: 124 pytest tests passed; Ruff lint and format passed; Pyright returned zero errors/warnings. Both Compose configurations render the host bind mount correctly. A real `load_from_toml`/FastAPI lifespan smoke check loaded all eight plugins, bootstrapped an empty temporary database, returned expected errors for unconfigured/invalid requests, and shut down the health task cleanly.
- Live QQ and Cloudflare delivery require deployment credentials and are documented as deployment checks; no external messages or production configuration were changed.
