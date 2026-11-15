# Phase 1 · Spec 10 — CI workflow + README quick start

**Suggested implementer:** `quick-implementer`
**Depends on:** 01–09 (all merged and green locally)

## Goal
Make "tests pass in CI" (PLAN.md §9 Phase 1) true: one GitHub Actions workflow that runs lint, the full test suite against a real Postgres/pgvector service container with the fake model, and the 10-case eval — with no secrets. Update the README so a newcomer can run the Phase 1 demo.

## Files
| Path | Action | Purpose |
|---|---|---|
| `.github/workflows/ci.yml` | create | the workflow below |
| `README.md` | modify | status line, Phase 1 quick start |
| `CLAUDE.md` | modify | lint command covers the new top-level packages |

## Interfaces

### `.github/workflows/ci.yml` (verbatim)
```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    services:
      db:
        image: pgvector/pgvector:0.8.0-pg17
        env:
          POSTGRES_USER: supportkit
          POSTGRES_PASSWORD: supportkit-dev
          POSTGRES_DB: supportkit
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U supportkit -d supportkit"
          --health-interval 2s --health-timeout 3s --health-retries 30
    env:
      DATABASE_URL: postgresql://supportkit:supportkit-dev@localhost:5432/supportkit
      LANGGRAPH_STRICT_MSGPACK: "true"
      SUPPORTKIT_MODEL: "fake:rules"
      SUPPORTKIT_DEMO_MODE: "false"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          python -m pip install uv
          python -m uv sync --frozen
      - name: Lint
        run: .venv/bin/ruff check src tests db seed evals ui
      - name: Migrate and seed
        run: |
          .venv/bin/supportkit migrate
          .venv/bin/supportkit seed
      - name: Tests (must not skip DB tests)
        run: |
          .venv/bin/python -m pytest -q -rs | tee pytest.out
          ! grep -q "Postgres not reachable" pytest.out
      - name: Evals (fake model, free)
        run: .venv/bin/supportkit eval --model fake:rules --require-all
```

### `README.md`
- Status line → `Currently at **Phase 1** (smallest end-to-end slice: order-status tool, Postgres-checkpointed graph, demo chat).`
- Replace the quick-start section with these commands (keep the Docker/WSL2 note and the integration-test note):
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
- Add a short "Models" paragraph: default `SUPPORTKIT_MODEL=fake:rules` is a deterministic rule-based stand-in (not an LLM); set `SUPPORTKIT_MODEL=anthropic:<model-id>` and `ANTHROPIC_API_KEY` for a real model.
- Add a short "Demo mode" paragraph: `/chat` exists only with `SUPPORTKIT_DEMO_MODE=true`, trusts `X-Demo-*` headers, and must never be exposed publicly; real channels (LINE) arrive in Phase 3.
- Add a PowerShell note: `$env:SUPPORTKIT_DEMO_MODE='true'; uv run supportkit serve`.

### `CLAUDE.md`
- Lint command → `.\.venv\Scripts\ruff.exe check src tests db seed evals ui`
- Add under Commands: `Seed: .\.venv\Scripts\supportkit.exe seed` and `Evals: .\.venv\Scripts\supportkit.exe eval --require-all`.

## Behaviour
1. The workflow uses no secrets and makes no LLM API call, so it is safe on fork PRs.
2. The "must not skip" guard fails the job if any DB-backed test skipped because Postgres was unreachable.
3. No real-model eval step in Phase 1 (PLAN.md §8 adds the smoke eval with a spend cap in Phase 5).

## Tests
No new unit tests. Verification is the local dry run below.

## Acceptance criteria
```powershell
.\.venv\Scripts\python.exe -c "import yaml; d = yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8')); assert 'test' in d['jobs']; print('ok')"
.\.venv\Scripts\ruff.exe check src tests db seed evals ui                    # All checks passed
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q -rs   # all pass; no "Postgres not reachable" skips
.\.venv\Scripts\supportkit.exe eval --model fake:rules --require-all         # exit 0
```
The workflow itself can only be confirmed once the repository is pushed to GitHub (the working directory is not yet a git repository) — report this as not verified rather than claiming a green run.

## Out of scope
- `git init`, commits, pushes, branch protection, badges.
- Dockerfile/docker-compose changes, an `app` compose service (Phase 6).
- Any change under `src/`, `seed/`, `evals/`, `ui/`, `tests/`.
