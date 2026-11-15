# supportkit — working agreement for Claude

Config-driven LangGraph customer-support agent for Thai online shops. `PLAN.md` is the source of truth. It is git-ignored and local only. `docs/phase0-spikes.md` records the verified versions and LINE API facts.

## Model delegation

The main session is the **orchestrator**. It routes work to project subagents (`.claude/agents/`) and checks their results. Subagents run in the background and report back to the orchestrator, not to the user.

| Work | Agent | Model |
|---|---|---|
| Design, analysis, planning, turning a phase into specs, reviewing diffs, hard bugs | `architect` | Fable 5.2 |
| Eval datasets, judges, thresholds, analyzing eval runs, regression verdicts | `evaluator` | Fable 5.2 |
| Implementing specs with real logic (LangGraph nodes, tools, tenancy/security, LINE adapter, async) | `implementer` | Sonnet 5.5 |
| Mechanical tasks (boilerplate, seed data, simple CRUD, renames, lint, docs) | `quick-implementer` | Haiku 5.5 |

### Standard loop per phase
1. **architect** reads PLAN.md and writes specs to `docs/specs/<phase>-<name>.md`, each tagged with a suggested implementer.
2. The orchestrator shows the user the spec list. Proceed once approved, unless the user already said to continue.
3. **implementer** or **quick-implementer** does one spec per run. Specs that touch different files may run in parallel. Specs that share files run one after another.
4. **architect** reviews each diff against its spec. Rejected diffs go back to the same implementer with the review notes.
5. **evaluator** runs or extends the evals at the end of the phase and gives a verdict.
6. The orchestrator verifies (runs the tests itself, reads the diff) and reports to the user. Never relay a subagent's "done" without checking.

### Routing rules
- Anything touching tenancy, security, `interrupt()` or graph routing goes to `implementer`, never to `quick-implementer`.
- If an implementer reports a spec ambiguity, send it to `architect`. Implementers never make design decisions.
- Small fixes (one file, a few lines, obvious) the orchestrator may do directly. Spawning an agent costs more.
- Escalate model tier rather than looping. If `quick-implementer` fails twice, give the task to `implementer`. If `implementer` fails twice, ask `architect` to rethink the spec.

## Commands (Windows, repo root)
- Tests: `$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q`
- Lint: `.\.venv\Scripts\ruff.exe check src tests db seed evals ui`
- DB: `docker compose up -d db`, then `.\.venv\Scripts\supportkit.exe migrate`, then `.\.venv\Scripts\supportkit.exe db-status`
- Seed: `.\.venv\Scripts\supportkit.exe seed`
- Evals: `.\.venv\Scripts\supportkit.exe eval --require-all`
- Deps: `python -m uv add <pkg>` (uv is installed via pip, not on PATH)

## Hard rules
- No commits or pushes unless the user asks.
- Tenancy invariants are listed in `.claude/agents/architect.md`. Every agent enforces them.
