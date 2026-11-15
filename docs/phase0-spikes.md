# Phase 0 — Spike findings

Date: 2026-11-14. Status legend: ✅ confirmed · ⏳ pending · ⚠ changes the plan

## 1. Installed versions (from `uv.lock`)

| Package | Version |
|---|---|
| langgraph | 1.2.22 |
| langgraph-checkpoint | 4.3.2 |
| langgraph-checkpoint-postgres | 3.2.1 |
| langchain / langchain-core | 1.5.0 / 1.8.0 |
| psycopg | 3.3.9 |
| line-bot-sdk | 3.27.0 |
| fastapi | 0.162.7 |
| alembic | 1.20.1 |
| pydantic | 2.14.3 |

✅ Verified in code: `interrupt(value, *, response_schema=None)` exists; `Runtime`, `PostgresSaver`/`AsyncPostgresSaver`, `PostgresStore`/`AsyncPostgresStore` import from the documented paths.

**Python:** Docker uses 3.12 (pinned in the `Dockerfile`). Local dev uses the system 3.13.1, because uv's managed-Python download failed on this machine ("Missing expected target directory for Python minor version link"). The lockfile covers both, since `requires-python = ">=3.11,<3.14"`. No `.python-version` file for now.

## 2. LINE Reply API change in Thailand ✅ ⚠

Read at the source: [LINE for Business TH notice, 30 Oct 2026](https://www.lineforbusiness.com/th/news/20261030).

- From **1 Feb 2027**, the Reply API runs on the Agency Global Platform (AGP).
- **25,000 free reply messages per month per OA.** The quota resets monthly and does not carry over.
- Above the quota: an **Unlimited plan at THB 5,000/month** through an Agency Partner. Other rates will be announced later.
- Continued Reply API use **requires registration through a LINE-designated Agency Partner**. There is no migration fee and no extra agency fee. The partner list has not been published yet.
- **Not stated:** how messages are counted (per request or per message object), and what happens to accounts that don't register.
- Auto-responses configured in LINE OA Manager are distinct from the Reply API, and the notice does not say they are affected.

**Plan impact:**
- Count reply and push calls per shop in `usage_events` from Phase 3 onward. This is already in the plan; now it is required.
- Batch up to 5 message objects into one reply request, in case counting turns out to be per request.
- Add "register the OA with an Agency Partner" to the client onboarding checklist (private repo).
- Most SMEs should stay under 25,000 replies/month, but debounce (merging rapid messages into one turn) now also saves quota.

## 3. Reply token and webhook `mode` ✅

From the [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/):
- Reply tokens are **single-use** and must be used **within 1 minute** of receiving the webhook. The limit may change without notice.
- Redelivered webhooks: the token is usable within 1 minute of the redelivery, unless it was already used or **20 minutes** have passed since the original event.
- The signature arrives in the `x-line-signature` header and must be checked before any event is processed.
- `mode: "active"`: the bot may send reply/push. `mode: "standby"`: **no reply token**, another module may be handling the user, and the bot **should not send messages**. → The adapter must ignore `standby` events for replies (store them only).

**Plan impact:** with a 3 s debounce plus a graph run, staying under 1 minute is realistic. Anything later (staff approval, slow LLM) uses push, which is already the plan. Fall back to push if the token is older than ~50 s instead of trying and failing.

## 4. LINE OA Chat + Webhook coexistence ⏳ (needs you)

This needs a real trial LINE OA and a Messaging API channel. I can't create the account. Test checklist:

1. In LINE OA Manager → Response settings, turn on **both** Chat and Webhook (Bot mode with manual chat available, depending on the current UI).
2. Point the webhook at a temporary endpoint that logs requests (Phase 0 has no app server yet — I can add a 20-line echo endpoint when you're ready).
3. Send a message from a personal LINE account. Check that the webhook fires **and** the message appears in the OA chat inbox.
4. Reply from the LINE OA app as staff. Check that the customer receives it, and confirm whether any webhook fires (expected: none).
5. While the chat is open in the OA app, check whether webhook events still arrive and what `mode` they carry.
6. Note the exact menu names in the current UI for `docs/adding-a-client.md`.

**If step 3 or 4 fails:** fall back to staff replying through our staff page (sent as push), as described in PLAN.md section 10.

## 5. Postgres + migrations ✅

Verified on 2026-11-14 after the Docker fix below:
- From an empty volume, `docker compose up -d db` followed by `docker compose up migrate` produces Postgres 17.6 with `vector` 0.8.0, `alembic_version`, `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `store` and `store_migrations`.
- `supportkit migrate` is idempotent: a second run from the host changes nothing and exits 0.
- The migrate service runs in the image on Python 3.12.16 with langgraph 1.2.22, the same lockfile as the host's 3.13.

**Interrupt/resume spike** (`tests/integration/test_interrupt_resume_postgres.py`, run with `LANGGRAPH_STRICT_MSGPACK=true`). All three tests pass against real Postgres:
- `interrupt(..., response_schema=StaffDecision)` pauses and returns `__interrupt__`. A **fresh checkpointer connection** (simulating a restart) still sees `next == ("human_handoff",)`. `Command(resume={"action": "edit", ...})` completes with the staff text. This is the core of the handoff design.
- An invalid resume value raises `pydantic.ValidationError` and leaves the thread paused. A correct resume afterwards succeeds.
- `checkpointer.delete_thread()` leaves zero rows in `checkpoints`. This is the building block for "forget me".

Integration tests skip themselves when Postgres isn't reachable, so `pytest` stays green on machines without Docker.

### Docker fix (historical)

**Cause found:** the Windows **"Virtual Machine Platform"** optional component is not enabled. The Docker Desktop log shows `HCS_E_SERVICE_NOT_AVAILABLE` ("a required feature is not installed"), and `wsl --status` says WSL2 is not supported in the current configuration. BIOS virtualization is already on (`VirtualizationFirmwareEnabled: True`), but no hypervisor is running and the `vmcompute` service is missing. Docker Desktop 4.31.1 (WSL2 backend) can't start any VM until this is fixed. It is a machine setting with admin rights and a reboot, so the machine owner does it: `wsl --install --no-distribution` in an elevated terminal, then reboot.

To finish this step once Docker is up:

```bash
docker compose up -d db
uv run supportkit migrate
uv run supportkit db-status
```

Expected: the `vector` extension, `alembic_version`, the checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`), and the store tables (`store`, `store_migrations`).
