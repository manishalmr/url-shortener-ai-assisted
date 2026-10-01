# Three Scenarios: Greenfield, Brownfield, Ambiguous

Per the assignment's required deliverable, this document walks through one scenario of each
type end-to-end. Unlike a purely narrative write-up, every transcript below was captured from
an actual `python run_pipeline.py --scenario ...` execution, not hand-written - reproduce any of
them yourself with the commands shown.

---

## Scenario 1 (Greenfield): Build a new capability from scratch

### Setup
`run_greenfield()` in `run_pipeline.py` seeds a fresh `PipelineContext` with
`feature_request="Add an endpoint that reverses a given string"` and no pre-existing target
file (nothing for `architecture_design` to treat as brownfield).

### Command
```bash
python run_pipeline.py --scenario greenfield
```

### What happens
All 8 tasks execute in dependency order, `implementation` and `documentation` run in the same
parallel batch (neither depends on the other), `quality_gate` fans back in once all three of
`implementation`/`test_writing`/`documentation` are done, and `human_approval` auto-approves
(non-interactive mode).

### Actual output (captured verbatim)
```
======================================================================
RUN COMPLETE: greenfield-28587a14
======================================================================

--- Decision lineage (ctx.history) ---
  [test_writing] entry_gate: implementation_exists: ok
  [quality_gate] exit_gate: quality_gate: ok
  [human_approval] entry_gate: release_approval: approved by human reviewer

--- Reliability metrics ---
{
  "run_id": "greenfield-28587a14",
  "total_latency_seconds": 0.017,
  "success_rate": 1.0,
  "retry_count": 0,
  "retry_frequency": 0.0,
  "rollback_count": 0,
  "mttr_seconds": 0.0,
  "total_attempts": 8,
  "distinct_tasks": 8
}

--- Audit log: 11 events recorded ---
```

### Validation
- `pipeline/workspace/greenfield-*/` contains real generated artifacts:
  `feature_add_an_endpoint_that_reverses_a_given_st.py`, its test file, a `.md` doc, and
  `RELEASE_NOTES.md` - all written by the actual agent functions, not mocked.
- `success_rate: 1.0`, `retry_count: 0` - a clean run, as expected with no failure injection.
- `tests/test_pipeline_integration.py::test_greenfield_pipeline_completes_successfully` asserts
  the same shape programmatically (all 8 outputs present, `released is True`).

---

## Scenario 2 (Brownfield): Extend an existing module, with a real reliability failure mode

### Requirement (as it would arrive in a real sprint)
"Extend `existing_module.py` with a subtract capability." Unlike greenfield, `architecture_design`
is given a real pre-existing file (`pipeline/sample_target/existing_module.py`) to inspect - it
parses out the existing function names (`greet`, `add`) so the plan reflects genuine
codebase-reasoning rather than working in a vacuum.

This scenario is also where the orchestrator's **reliability controls** (retry, rollback,
safe-stop) get exercised, using a deterministic failure-injection hook in `implementation()`
(`ctx.inputs["_fail_implementation_times"]` / `["_force_fail_implementation"]`) so the two
outcomes below are reproducible on demand rather than dependent on real, flaky failures.

### 2a. Recoverable failure -> bounded retry succeeds

#### Command
```bash
python run_pipeline.py --scenario brownfield --fail-implementation-times 2
```

#### Actual output (captured verbatim)
```
======================================================================
RUN COMPLETE: brownfield-7d0ead16
======================================================================

--- Decision lineage (ctx.history) ---
  [implementation] task_exception: Simulated TRANSIENT implementation failure on attempt 1 (demo of bounded retries succeeding)
  [implementation] task_exception: Simulated TRANSIENT implementation failure on attempt 2 (demo of bounded retries succeeding)
  [test_writing] entry_gate: implementation_exists: ok
  [quality_gate] exit_gate: quality_gate: ok
  [human_approval] entry_gate: release_approval: approved by human reviewer

--- Reliability metrics ---
{
  "run_id": "brownfield-7d0ead16",
  "total_latency_seconds": 0.241,
  "success_rate": 1.0,
  "retry_count": 2,
  "retry_frequency": 0.25,
  "rollback_count": 0,
  "mttr_seconds": 0.212,
  "total_attempts": 10,
  "distinct_tasks": 8
}
```
`implementation` (`max_retries=2`) fails on attempts 1 and 2, succeeds on attempt 3 - within
budget, so the pipeline completes normally. `retry_count: 2`, `mttr_seconds` reflects the real
wall-clock time lost to the two failed attempts + backoff before recovery.

### 2b. Permanent failure -> retries exhausted -> rollback -> safe-stop

#### Command
```bash
python run_pipeline.py --scenario brownfield --force-fail-implementation
```

#### Actual output (captured verbatim)
```
*** SAFE-STOP TRIGGERED: Safe-stop triggered by task 'implementation': critical task exhausted retries ***
Pipeline halted safely - no partial release occurred.
[
  {
    "task_id": "implementation",
    "event": "retry",
    "detail": "attempt 1 failed (Simulated PERSISTENT implementation failure ...); retrying"
  },
  {
    "task_id": "implementation",
    "event": "retry",
    "detail": "attempt 2 failed (Simulated PERSISTENT implementation failure ...); retrying"
  },
  {
    "task_id": "implementation",
    "event": "retries_exhausted",
    "detail": "Simulated PERSISTENT implementation failure ..."
  },
  {
    "task_id": "implementation",
    "event": "rollback",
    "detail": "rollback_fn executed"
  },
  {
    "task_id": "orchestrator",
    "event": "safe_stop",
    "detail": "critical task exhausted retries"
  }
]
```

**Confirmed via the actual filesystem, not just the log**: `implementation()` writes its
artifact file *before* the simulated-failure check can raise, so a failed/exhausted attempt
leaves a partial file on disk. After this run, `pipeline/workspace/brownfield-<id>/` contains
only `feature_extend_existing_module_with_a_subtract_c.md` (from the independently-completed
`documentation` task) - the `.py` implementation file and its test are **absent**, because
`_rollback_implementation()` genuinely deletes the partial artifact, and `test_writing`/
`quality_gate`/`human_approval`/`release_readiness` never ran (the orchestrator halted at the
first critical failure, before their batch). This is a real compensating action being proven,
not a hook that exists only for show.

### Validation
- `tests/test_pipeline_integration.py::test_brownfield_bounded_retry_recovers` and
  `::test_brownfield_permanent_failure_safe_stops_and_rolls_back` assert both paths
  deterministically.
- `tests/test_executor.py` covers the retry/rollback/safe-stop mechanics in isolation, with
  synthetic tasks, independent of this specific pipeline.

---

## Scenario 3 (Ambiguous requirement): "Make it better" -> clarify -> dynamic re-plan

### Requirement as given
`"make it better"` - no target, no scope, no acceptance criteria. This is the same class of
ambiguity the AI-Assisted project's QR-code scenario dealt with, but here the orchestrator
itself has to *detect* the ambiguity and support the pipeline being re-run once it's resolved,
rather than a human resolving it once up front before any code runs.

### Command
```bash
python run_pipeline.py --scenario ambiguous
```

### What happens
1. `requirements_analysis` flags the request as ambiguous (matches a vague-language marker list
   / too few words) and records explicit assumptions instead of guessing silently and pressing
   on.
2. The full pipeline runs once, end to end, under those assumptions.
3. A stakeholder then clarifies: `feature_request` is mutated to `"Add a function that reverses
   a given string"`, and `ctx.dirty_tasks.add("requirements_analysis")` is set - this is an
   **externally-triggered** change (see `architecture.md` §3), so `requirements_analysis`
   itself must re-run, not just its downstream consumers.
4. `orchestrator.run(graph, ctx)` is called a **second time on the same context**. Because
   `ctx.completed_tasks` persists across calls, only `requirements_analysis` and everything
   downstream of it re-executes - the orchestrator doesn't redo work needlessly, but does redo
   everything that could be affected by the changed input.

### Actual output (captured verbatim)
```
--- Initial (ambiguous) run ---
Ambiguity detected: True
Assumptions made: ['Interpreting the vague request as: add a small, additive utility function rather than a breaking change.', 'No UI/API contract changes assumed unless explicitly stated.']

--- Stakeholder clarifies the requirement; triggering dynamic re-plan ---
Ambiguity after clarification: False

======================================================================
RUN COMPLETE: ambiguous-c29314c5
======================================================================

--- Decision lineage (ctx.history) ---
  [test_writing] entry_gate: implementation_exists: ok
  [quality_gate] exit_gate: quality_gate: ok
  [human_approval] entry_gate: release_approval: approved by human reviewer
  [orchestrator] manual_replan_trigger: Stakeholder clarified the requirement
  [orchestrator] replan_triggered: Upstream change in ['requirements_analysis'] -> re-running ['architecture_design', 'documentation', 'human_approval', 'implementation', 'quality_gate', 'release_readiness', 'requirements_analysis', 'test_writing']
  [test_writing] entry_gate: implementation_exists: ok
  [quality_gate] exit_gate: quality_gate: ok
  [human_approval] entry_gate: release_approval: approved by human reviewer

--- Reliability metrics ---
{
  "run_id": "ambiguous-c29314c5",
  "total_latency_seconds": 0.012,
  "success_rate": 1.0,
  "retry_count": 0,
  "rollback_count": 0,
  "total_attempts": 8,
  "distinct_tasks": 8
}
```

Note the `replan_triggered` event lists **all 8 tasks** as affected - correct, because
`requirements_analysis` is the graph's root, so its downstream closure is the entire pipeline.
Exactly one replan cycle occurs (the loop condition clears after this pass and nothing else
marks the context dirty), and the re-run's own `RunMetrics` (a fresh object per `.run()` call)
correctly shows all 8 tasks executing again with `success_rate: 1.0`.

### A real bug found and fixed while building this
Before this worked, `Orchestrator.run()` tracked completed tasks in a local variable that reset
on every call - so a second `.run()` on the same context would have either redone the entire
graph from scratch or mis-tracked which tasks were genuinely still pending. Moving that state
onto `ctx.completed_tasks` (persists across calls, by design) fixed it. Caught while writing
`tests/test_pipeline_integration.py::test_ambiguous_requirement_clarification_triggers_replan`
- the same "write the test, notice it wouldn't actually prove what I think" discipline used
throughout the main AI-Assisted project.

### Validation
- `tests/test_pipeline_integration.py::test_ambiguous_requirement_flags_ambiguity_and_records_assumptions`
  and `::test_ambiguous_requirement_clarification_triggers_replan` assert this deterministically.
- `tests/test_executor.py::test_dynamic_replanning_reruns_downstream_tasks` and
  `::test_dirty_task_reruns_itself_and_downstream` isolate the `stale_tasks` vs. `dirty_tasks`
  semantics against synthetic tasks, independent of this specific pipeline.
