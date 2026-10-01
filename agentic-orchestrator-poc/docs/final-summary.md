# Final Engineering Summary

## Context & plan
This is an **extra-credit** build, undertaken after the required
[AI-Assisted assignment](../README.md) was already complete, tested, documented, and verified.
The brief for the "Agentic" variant asks for an autonomous orchestration engine (dependency
graph, gates, retries/rollback, dynamic re-planning, audit-grade observability) coordinating
multiple stages - normally a multi-week production build. Given roughly a day, the plan was:

1. Build the **orchestration engine itself** as a small, generic, reusable core
   (`orchestrator/`) - independent of any specific pipeline - so it genuinely proves the hard
   mechanical parts (DAG execution, gating, bounded retry, rollback, safe-stop, two distinct
   re-planning semantics, structured observability) rather than hard-coding behavior into one
   demo script.
2. Wire it up to a small but real demo pipeline (`pipeline/`) modeling an SDLC flow, with stages
   that do genuine, checkable work (real files written/read/validated) so gates and rollback have
   something real to act on.
3. Demonstrate the three required scenario types **live**, via an actual CLI run, not just in
   unit tests - same standard of proof applied throughout the primary assignment.
4. Apply the same quality gates as the primary project (tests + lint) and document scope
   explicitly rather than let a time-boxed PoC quietly masquerade as a finished product.

## Artifacts produced
- Working orchestration engine (`orchestrator/`) + demo SDLC pipeline (`pipeline/`) - runnable
  locally via `run_pipeline.py`.
- 32 automated tests, 96% line coverage, 0 lint errors (`ruff`).
- All three required scenarios executed live via the CLI with captured, reproducible transcripts
  (`docs/scenarios.md`), including proof (via real filesystem state) that rollback performs a
  genuine compensating action, not a no-op.
- Architecture documentation with component diagram and a full requirements-to-code mapping
  (`docs/architecture.md`).
- Explicit scope/limitations write-up distinguishing "PoC of the mechanics" from "production
  system" (`docs/limitations.md`).
- Setup instructions and usage reference (`README.md`).

## What was verified, not just claimed
| Claim | How it was verified |
|---|---|
| DAG executes with correct parallel/sequential ordering | `test_graph.py` + live runs show `implementation`/`documentation` genuinely running in the same batch |
| Bounded retries recover from transient failures | Live run with `--fail-implementation-times 2`: 2 failures, 2 retries, then success (`retry_count: 2` in captured metrics) |
| Rollback performs a real compensating action | Live run with `--force-fail-implementation`: confirmed via the actual workspace folder that the partial implementation file was deleted |
| Safe-stop halts cleanly on critical failure | Same run: `release_readiness` never executed, no partial release artifact produced |
| Dynamic re-planning re-runs only the affected subset | Live ambiguous-scenario run: exactly one `replan_triggered` event, listing the correct downstream closure, ambiguity resolved from `True` to `False` |
| `stale_tasks` vs. `dirty_tasks` semantics are distinct and correct | `test_dynamic_replanning_reruns_downstream_tasks` (downstream-only) vs. `test_dirty_task_reruns_itself_and_downstream` (includes the task itself) |
| Audit-grade observability | Every run produces a JSONL audit log + a `RunMetrics.summary()` with success rate, retry frequency, rollback count, MTTR, total latency |

## Risks, trade-offs, and how they were handled
| Risk | Mitigation |
|---|---|
| Conflating two different "replan" triggers (self-signaled vs. externally-triggered) - found while writing tests, not in production | Split into `stale_tasks`/`dirty_tasks` as two explicit fields with distinct re-run semantics, each independently tested |
| `Orchestrator.run()` not correctly supporting being called twice on the same context (a real bug found mid-build) | Moved completion tracking onto `ctx.completed_tasks` (persists across calls) instead of a per-call local variable; re-verified all tests + all three live scenarios after the fix |
| Scope creep risk (this could balloon into a multi-week effort) | Explicit time-box (~1 day) and PoC framing agreed up front; `limitations.md` states exactly what's deferred and why, rather than silently under-delivering or over-claiming |
| A stubbed-out "agent" pipeline would prove nothing about the real orchestration mechanics | Every stage does genuine work (parses text/files, writes real artifacts, validates them) so gates/retries/rollback are exercised against real outcomes |

## Assumptions
- "Agents" are simulated as deterministic Python functions rather than live LLM calls, per the
  explicit time-box; the orchestration mechanics (the actual subject of this assignment variant)
  are unaffected by what's inside each stage function - see `limitations.md` for the swap-in
  path.
- A single in-process CLI run is sufficient to demonstrate every required mechanic; durable
  cross-process persistence was out of scope for a 1-day PoC.
- The existing AI-Assisted project and its git history were not to be touched by this work, and
  were not touched - this project is fully self-contained in `agentic-orchestrator-poc/`.

## Engineering judgment demonstrated
- Chose to fully finish and verify a deliberately smaller surface area (the orchestration engine
  itself, one demo pipeline, three live-run scenarios) rather than sketch a larger, unverified one
  - consistent with the standard applied to the required deliverable.
- Found and fixed a real state-management bug (`completed_tasks` not persisting across `.run()`
  calls) through the same "write the test, notice it doesn't prove what I think" discipline used
  throughout, then re-verified the fix live, not just via unit tests.
- Documented scope honestly: this is explicitly framed as a PoC of the orchestration mechanics,
  not a production-ready agentic platform, with a concrete, low-effort path from one to the other
  laid out in `limitations.md`.
