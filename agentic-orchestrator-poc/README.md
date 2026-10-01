# Agentic Orchestrator - Proof of Concept

A working, tested proof-of-concept of an **autonomous orchestration engine** that coordinates
multiple "agent" stages through an explicit dependency graph, with gates, bounded retries,
rollback, dynamic re-planning, and audit-grade observability - the "Agentic Software Engineer"
assignment variant.

> **Scope note**: this is a deliberately time-boxed extra-credit build (about a day), done
> *after* completing the primary [AI-Assisted assignment](../README.md) as the required
> deliverable. It proves the orchestration mechanics end-to-end with deterministic stand-in
> "agents" rather than live LLM calls per stage. See
> [`docs/final-summary.md`](docs/final-summary.md) for exactly what's in scope vs. deferred, and
> why. This project is fully independent of the AI-Assisted project - nothing there was touched.

## Documentation index

| Doc | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Component diagram, the orchestration engine's mechanics, key design decisions |
| [`docs/scenarios.md`](docs/scenarios.md) | Greenfield / brownfield / ambiguous-requirement walkthroughs, run live via the CLI |
| [`docs/limitations.md`](docs/limitations.md) | What's simplified for the PoC, and the upgrade path to production |
| [`docs/final-summary.md`](docs/final-summary.md) | Scope, artifacts, what was verified, what's deferred |

## Quick start

```bash
cd agentic-orchestrator-poc
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements-dev.txt
```

### Run the three required scenarios

```bash
python run_pipeline.py --scenario greenfield
python run_pipeline.py --scenario brownfield --fail-implementation-times 2   # recovers via retry
python run_pipeline.py --scenario brownfield --force-fail-implementation     # exhausts retries -> rollback -> safe-stop
python run_pipeline.py --scenario ambiguous                                  # detects ambiguity -> clarifies -> dynamic re-plan
```

Add `--interactive` to any of these to be prompted for a real human approval decision
(`y`/`N`) at the release-approval gate, instead of auto-approving.

### Run the tests

```bash
pytest                          # 32 tests + coverage report
ruff check orchestrator pipeline tests run_pipeline.py   # lint
```

## What it orchestrates

The demo pipeline (`pipeline/demo_pipeline.py`) models a small software-delivery lifecycle as an
explicit task graph:

```
requirements_analysis -> architecture_design -> [implementation, documentation] (parallel)
    -> test_writing (depends on implementation) -> quality_gate (fan-in)
    -> human_approval (gate) -> release_readiness
```

Every stage does **real, verifiable work** (parses requirement text, inspects an existing file
for the brownfield scenario, writes real implementation/test/doc files to a workspace folder,
validates them) - see [`docs/architecture.md`](docs/architecture.md) for why that matters and
[`docs/limitations.md`](docs/limitations.md) for what it deliberately isn't (live LLM calls).

## Project structure

```
orchestrator/
  task.py            # Task definition: deps, gates, retries, rollback hook
  graph.py           # Explicit DAG, topological batching (Kahn's algorithm)
  gates.py           # AutomatedGate (predicate-based) + HumanApprovalGate
  context.py         # Cross-stage state, decision lineage, replan signals
  executor.py        # Orchestrator: parallel execution, retries, rollback, safe-stop, re-planning
  observability.py   # Audit log (JSONL) + reliability metrics (success rate, MTTR, ...)
  policy.py          # Regex-based guardrails on generated code (banned patterns)
pipeline/
  sdlc_agents.py     # The 6 "agent" stage functions
  demo_pipeline.py   # Wires the stages into the graph above, with real gates
  sample_target/     # Pre-existing module used for the brownfield scenario
tests/               # 32 tests, 96% coverage
run_pipeline.py      # CLI entry point for the three scenarios
docs/                # Deliverables (see index above)
```

## Requirements traceability

Every module docstring states the specific requirement it satisfies (search for "Requirement
being satisfied" across `orchestrator/*.py`) so the mapping from assignment brief to code is
explicit rather than implied.
