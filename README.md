# supportkit

Config-driven AI customer support agent for Thai online shops, built with LangGraph.

> Work in progress. Currently at **Phase 1** (smallest end-to-end slice: order-status tool, Postgres-checkpointed graph, demo chat).

## Quick start (dev)

Requires Docker (on Windows: WSL2 with "Virtual Machine Platform" enabled).

```bash
cp .env.example .env
docker compose up -d db
uv sync
uv run supportkit migrate
uv run supportkit seed
uv run pytest
uv run supportkit eval --require-all            # 10 cases, built-in fake model, no API key

# demo (two terminals)
SUPPORTKIT_DEMO_MODE=true uv run supportkit serve
uv run streamlit run ui/demo_chat.py
```

On PowerShell, set the demo flag inline: `$env:SUPPORTKIT_DEMO_MODE='true'; uv run supportkit serve`

To run migrations inside the container instead of on the host: `docker compose run --rm migrate`.

Integration tests in `tests/integration/` need Postgres plus `supportkit migrate` and `supportkit seed`, and are skipped when Postgres is unreachable (CI fails on any skip).

## Models

The default `SUPPORTKIT_MODEL=fake:rules` is a deterministic rule-based stand-in, not an LLM. To use a real model, set `SUPPORTKIT_MODEL=anthropic:<model-id>` and `ANTHROPIC_API_KEY`.

## Demo mode

`/chat` exists only with `SUPPORTKIT_DEMO_MODE=true`. It trusts `X-Demo-*` headers, so it must never be exposed publicly. Real channels (LINE) arrive in Phase 3.
