# Kuma health Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Report real QQ bot health to an existing Kuma Push monitor.

**Architecture:** A NoneBot plugin owns one asyncio task and HTTPX client.
It probes configured QQ bots before each push and cancels cleanly at shutdown.

**Tech Stack:** Python 3.10+, NoneBot 2, QQ adapter, HTTPX, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-kuma-health-design.md`

## Global Constraints

- `KUMA_PUSH_URL` configures one existing monitor; empty disables checks.
- Check immediately and every 60 seconds, with bounded requests.
- Both WebSocket readiness and a successful live identity request are required.
- Retain the earlier `bot.py` startup fix and avoid live QQ/Kuma requests in tests.

## Review Focus

- No bots, partially connected bots, or Webhook mode must never report up.
- API exceptions and timeouts must report down without stopping future checks.
- Disconnection during the identity request must not produce an up result.
- A copied Push URL's status parameters must be replaced, not duplicated.
- Failed delivery and shutdown must not leak tasks, clients, or Push tokens.

### Task 1: Plugin, tests and usage

**Files:** Create `src/plugins/kuma_health/{__init__,config,health}.py` and
`tests/test_kuma_health.py`; update `.env.example` and `README.md`.

**Interfaces:** `check_health() -> tuple[Literal["up", "down"], str]`,
`report_health(client: httpx.AsyncClient) -> None`,
`start_health_task() -> None`, `stop_health_task() -> None`.

- [x] Create scaffolding with `nb plugin create` and write failing behavioral tests.
- [x] Run the new tests; confirm missing health checks fail.
- [x] Implement the probe, Push query merging, task lifecycle and configuration.
- [x] Run the new tests and full suite; expect all tests to pass.
- [x] Document configuration and WebSocket requirement; run Ruff and Pyright,
      distinguishing existing repository issues from new ones.
- [x] Review the final diff for the five failure modes above.

Review found HTTPX INFO logs expose the Push URL; two failing log-capture
tests reproduced it. A request-scoped logging filter now hides those logs
without hiding unrelated HTTPX requests. Full suite: 49 passed.

### Task 2: Update project plugins and dependencies

The user's follow-up requests updates to all project plugins and dependencies.
Keep Python 3.10+ support and existing notification behavior.

- [x] Check current stable versions against PyPI; update runtime/dev version
      ranges and explicitly declare directly imported HTTPX, Pydantic and yarl.
- [x] Include NB CLI in development dependencies and align Ruff/Pyright with 3.10.
- [x] Update local plugins for current SDK types and lint rules without changing
      webhook routes or message behavior.
- [x] Back up the broken local virtual environment and install updated dependencies.
- [x] Run all tests, full Ruff checks, formatting, Pyright, dependency validation
      and safe plugin auto-loading; document usage and installed versions.

Final validation in the rebuilt Python 3.14 environment: 49 tests passed;
`ruff check .`, `ruff format --check .`, `pyright` and `git diff --check`
all passed. All 79 installed packages are compatible, and all five local
plugins load with the WebSocket-capable driver. Previous environment:
`/tmp/notification-bot-venv-backup-yhbuzsv0/venv`.
