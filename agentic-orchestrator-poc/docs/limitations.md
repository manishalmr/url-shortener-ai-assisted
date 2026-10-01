# Scope, Testing Approach & Limitations

## 1. Why this exists, and why it's scoped the way it is

The assignment's "Agentic" variant asks for a second system on top of a working product: a
dependency-graph orchestration engine with retries/rollback, approval gates, dynamic
re-planning, and audit-grade observability - roughly a 3-4 week production build, not a 1-day
one. This PoC was built as **extra-credit, after** the required
[AI-Assisted assignment](../README.md) was already complete, tested, and documented, explicitly
time-boxed to about a day. The goal was to prove the *hard mechanical parts* of an agentic
orchestrator work correctly, live, rather than describing them - not to deliver a
production-ready orchestration platform.

## 2. Testing approach

| Layer | Tool | What it covers |
|---|---|---|
| Unit | `pytest` | Graph construction/cycles (`test_graph.py`), gates (`test_gates.py`), metrics/audit log (`test_observability.py`) |
| Integration | `pytest` | Full executor behavior: retries, rollback, safe-stop, both re-planning semantics (`test_executor.py`) |
| End-to-end | `pytest` + real filesystem assertions | The full demo pipeline for all 3 scenario types, asserting real generated artifacts exist (`test_pipeline_integration.py`) |
| Coverage | `pytest-cov` | 96% line coverage |
| Lint | `ruff` | Style/bug-pattern checks (`E`, `F`, `I`, `UP`, `B` rule sets) - 0 findings |
| Manual E2E | `run_pipeline.py` CLI | All three scenarios executed live against the actual code, not just asserted in tests - see `scenarios.md` for captured transcripts |

Each test constructs its own isolated `PipelineContext` and (for pipeline-level tests) an
isolated `tmp_path` workspace, so tests never share state.

## 3. What's simplified for the PoC (and the upgrade path)

| Simplification | Why it exists | Production upgrade path |
|---|---|---|
| **Deterministic Python functions instead of live LLM calls** | Free, instant, 100% reproducible for grading/demo purposes; still exercises the real orchestration mechanics against genuine (not hardcoded) task outcomes | Replace each function body in `pipeline/sdlc_agents.py` with a call to an LLM API + structured-output parsing; the `Task`/gate/retry contract around it doesn't change at all - that's the point of the layering |
| **In-memory context, no durable checkpointing** | A single CLI process is enough to demonstrate replanning (run, mutate, run again on the same object) | Persist `PipelineContext` (outputs, history, completed_tasks) to a DB/object store between runs, so a long-running or crashed orchestration can resume rather than starting over |
| **Threads, not distributed workers** | The agent functions here are fast, synchronous file I/O; threads are the right-sized tool | For real LLM calls (network-bound, minutes not milliseconds) swap `ThreadPoolExecutor` for a task queue (Celery/Temporal/etc.) - the batching/dependency logic in `TaskGraph` is unchanged either way |
| **Regex-based policy guardrail** | Demonstrates the guardrail *mechanism* (an exit gate that can reject an artifact) without pulling in a heavy scanner for a 1-day PoC | Swap `scan_code_for_policy_violations` for a real call to `bandit`/`semgrep`/a secrets-scanner; it's already isolated behind one function and one exit gate, so nothing else changes |
| **In-process `HumanApprovalGate`, single reviewer** | Sufficient to prove the pause/resume-on-approval mechanic | Real approval would be a durable, addressable request (Slack/email/ticket) that the orchestrator polls or is webhooked back into, potentially with multiple required approvers |
| **No persistence/replay of the audit log beyond a JSONL file per run** | Enough to prove audit-grade traceability exists and is structured | Ship `AuditLog` events to a real log/observability pipeline (e.g. the same Datadog-style stack used elsewhere) for cross-run querying and alerting |
| **Single orchestrator process, no distributed coordination** | Out of scope for proving the DAG/gate/retry mechanics | Would need leader election / distributed locks if multiple orchestrator instances needed to coordinate on the same run |
| **No authentication/multi-tenancy** | Same rationale as the AI-Assisted project - out of scope for either exercise | Add an identity layer scoping runs/approvals to a tenant/user, same shape of change as the AI-Assisted project's deferred-auth note |

## 4. Trade-offs made explicitly

- **Real file-writing "agents" vs. pure in-memory stubs**: chose to have each stage do genuine,
  checkable work (write files, parse an existing module, validate outputs) specifically so gate
  checks and rollback have something real to succeed/fail/undo against - a stub that always
  returns `{"ok": True}` would prove nothing about whether the gating/retry/rollback logic
  actually works.
- **`stale_tasks`/`dirty_tasks` as two fields vs. one generic "needs replan" set**: more code, but
  makes an easy-to-get-wrong semantic distinction (does the signaling task re-run itself or not?)
  impossible to accidentally conflate - this was a real bug caught while writing tests, not a
  hypothetical concern.
- **Time-boxed scope vs. a more "complete-looking" but shallower build**: chose to fully finish
  and verify (tests + lint + live scenario runs) a smaller surface area rather than sketch a
  larger one that wasn't provably correct - same engineering discipline applied to the required
  AI-Assisted deliverable.

## 5. What was intentionally left out entirely (not started)

- A separate git repository for this sub-project (it currently lives alongside the AI-Assisted
  project, excluded from that project's git history via `.gitignore`).
- Any real LLM integration - see §3, this is the most valuable and most straightforward next
  step if this PoC were to be taken further.
- A web UI/API around the orchestrator (this is a CLI-driven demo by design, to keep the scope
  to the orchestration engine itself).
