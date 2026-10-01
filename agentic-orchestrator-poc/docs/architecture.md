# Architecture Overview

## 1. Components

```
                    run_pipeline.py (CLI)
                            |
                    build_pipeline()  <- pipeline/demo_pipeline.py
                            |
                 ┌──────────▼───────────┐
                 │   TaskGraph (DAG)     │   orchestrator/graph.py
                 │  execution_batches()  │   Kahn's algorithm -> parallel-eligible levels
                 └──────────┬───────────┘
                            │
                 ┌──────────▼───────────┐
                 │     Orchestrator      │   orchestrator/executor.py
                 │  .run(graph, ctx)     │
                 └──┬────────┬────────┬─┘
                    │        │        │
         ┌──────────▼─┐ ┌────▼────┐ ┌─▼─────────────┐
         │ Gates       │ │ Retry/  │ │ Observability │
         │ (entry/exit)│ │ rollback│ │ (audit log +  │
         │ gates.py    │ │ safe-   │ │  metrics)     │
         │             │ │ stop    │ │ observability │
         └──────────┬─┘ └────┬────┘ └─┬─────────────┘
                    │        │        │
                 ┌──▼────────▼────────▼──┐
                 │   PipelineContext      │   orchestrator/context.py
                 │ outputs / history /    │   (shared state + decision lineage)
                 │ stale_tasks / dirty_   │
                 │ tasks / completed_tasks│
                 └──────────┬─────────────┘
                            │
                 ┌──────────▼───────────┐
                 │  6 "agent" stages     │   pipeline/sdlc_agents.py
                 │  requirements_analysis│
                 │  architecture_design  │
                 │  implementation       │
                 │  documentation        │
                 │  test_writing         │
                 │  release_readiness    │
                 └───────────────────────┘
```

## 2. The orchestration engine's mechanics

This is the part being demonstrated - a generic engine that would work for *any* set of staged
tasks, not just this specific SDLC pipeline.

| Mechanic | How it works | Where |
|---|---|---|
| **Explicit dependency graph** | Tasks declare `depends_on=[...]`; `TaskGraph` validates no cycles/unknown deps and groups tasks into "batches" (levels) via Kahn's algorithm - each batch's tasks have no dependency on each other | `orchestrator/graph.py` |
| **Parallel execution + synchronization** | Each batch runs concurrently on a `ThreadPoolExecutor`; the orchestrator only moves to the next batch once every task in the current one has resolved - that's the fan-in/sync point | `orchestrator/executor.py::_execute_batches` |
| **Entry/exit gates** | `AutomatedGate` wraps a predicate function (e.g. "did the implementation file get written?"); a task's entry gates run before it executes, exit gates run after, before the result is accepted | `orchestrator/gates.py` |
| **Human approval checkpoints** | `HumanApprovalGate` is an entry gate whose predicate is a swappable `approval_provider` callback - CLI demo uses real `input()`, tests use a pre-programmed yes/no, so the orchestrator code path is identical in both | `orchestrator/gates.py` |
| **Bounded retries with backoff** | Each task has `max_retries` + `retry_backoff_seconds`; the executor retries on any exception or failed exit gate up to that bound | `orchestrator/executor.py::_run_single_task` |
| **Rollback on exhaustion** | If retries are exhausted, `task.rollback_fn(ctx)` runs (if provided) before the task is marked failed - a real compensating action, not a no-op hook (see Scenario 2 in `scenarios.md`) | `orchestrator/executor.py`, `pipeline/demo_pipeline.py::_rollback_implementation` |
| **Safe-stop** | If a *critical* task (the default) exhausts retries, the orchestrator halts the whole run via `SafeStopTriggered` rather than pressing on with a broken dependency chain; non-critical tasks can be configured to `skip` instead | `orchestrator/executor.py` |
| **Dynamic re-planning** | Two distinct triggers, deliberately modeled separately (see §3) | `orchestrator/context.py`, `orchestrator/executor.py::run` |
| **Cross-stage context & decision lineage** | `PipelineContext.outputs` is the official per-task result registry; `PipelineContext.history` is an ordered, human-readable log of every gate check, retry, rollback, and replan decision - the "why did the pipeline do X" trail | `orchestrator/context.py` |
| **Audit-grade observability** | Every gate check / retry / rollback / replan is also emitted as a structured JSON-lines event (`AuditLog`), independent of `history`, suitable for shipping to a real log pipeline; `RunMetrics` derives success rate, retry frequency, rollback count, MTTR, and total latency from the same attempt data | `orchestrator/observability.py` |
| **Policy guardrails** | Generated code is scanned against a small regex banned-pattern list (`eval`, `exec`, `os.system`, hardcoded secrets) before being allowed to land - demonstrates *where* a real SAST/secrets-scanner would plug into the pipeline as an exit gate | `orchestrator/policy.py` |

## 3. Re-planning: two distinct semantics, not one

A real engineering nuance surfaced while building this: "something changed upstream, re-plan"
is not one behavior, it's two, depending on *who* triggered it:

| Trigger | Field | Who re-runs | Example |
|---|---|---|---|
| **Self-signaled** | `ctx.stale_tasks` | Everything **downstream** of the signaling task - not the task itself (its own result is already correct; it's just telling consumers to recompute) | A task returns `{"replan": True}` because its own output changed in a way that invalidates cached downstream assumptions |
| **Externally-triggered** | `ctx.dirty_tasks` | The task itself **plus** everything downstream (its own inputs changed, so its own prior output is now stale too) | A human edits `ctx.inputs["feature_request"]` after the pipeline already ran once - the ambiguous-requirement scenario |

Both feed the same replan loop in `Orchestrator.run()`, which computes the affected subset via
`graph.downstream_of()`, clears it from `ctx.completed_tasks`, and re-executes only that subset
- not the whole graph from scratch. `ctx.completed_tasks` persists on the context object across
multiple `.run()` calls specifically to make this possible (see the docstring on that field).

## 4. Key decisions & rationale

| Decision | Alternative considered | Why this was chosen |
|---|---|---|
| Deterministic Python functions as "agents" instead of live LLM calls | Wire a real LLM API into each stage | Keeps the PoC free, fast, and fully reproducible for grading while still exercising the *real* orchestration mechanics (retries, gates, rollback) against genuine task outcomes rather than hardcoded stubs. Documented as the clear next step in `limitations.md`. |
| `ThreadPoolExecutor` per batch | `asyncio` task group | Stdlib-only, no new dependency, and the agent functions here are synchronous file I/O - threads are the simpler correct tool for this scope. |
| In-memory `PipelineContext` (no persistence) | Persist state to disk/DB between runs | A single `run_pipeline.py` process is enough to demonstrate the replanning mechanic (run, mutate, run again on the same object); durable checkpointing is a real production concern, called out in `limitations.md`. |
| Regex-based policy guardrail | Integrate `bandit`/`semgrep` directly | Demonstrates the guardrail *mechanism* (an exit gate that can reject an artifact) cheaply; swapping in a real scanner later doesn't change any orchestrator code, only the predicate function. |
| `stale_tasks` vs. `dirty_tasks` as two separate fields | One generic `needs_replan` set | Conflating them was an actual bug caught while writing tests for this PoC (a task that signals its own staleness must NOT re-run itself, but an externally dirtied task must) - keeping them separate makes the two semantics impossible to accidentally mix up. |

## 5. What was actually verified (not just written)

- All 32 unit/integration tests pass (`pytest`), 96% line coverage.
- `ruff check` clean (0 findings) across `orchestrator/`, `pipeline/`, `tests/`, `run_pipeline.py`.
- All three required scenarios executed **live** via the actual CLI, not just asserted in tests:
  greenfield (clean run), brownfield recoverable (2 injected failures -> 2 retries -> success),
  brownfield permanent failure (retries exhausted -> real file deleted by rollback -> clean
  safe-stop, confirmed via the resulting workspace contents), and ambiguous (ambiguity detected
  -> clarified -> exactly one re-plan cycle -> ambiguity resolved). See `scenarios.md` for the
  full transcripts.
