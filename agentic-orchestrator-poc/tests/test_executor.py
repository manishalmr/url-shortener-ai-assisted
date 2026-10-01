import pytest

from orchestrator.context import PipelineContext
from orchestrator.executor import Orchestrator, SafeStopTriggered
from orchestrator.gates import (
    AutomatedGate,
    HumanApprovalGate,
    auto_approve_provider,
    auto_reject_provider,
)
from orchestrator.graph import TaskGraph
from orchestrator.task import Task


def _ctx(**inputs) -> PipelineContext:
    return PipelineContext(run_id="test-run", inputs=inputs)


def test_sequential_and_parallel_execution_runs_all_tasks():
    calls = []

    def make_fn(name):
        def fn(ctx):
            calls.append(name)
            return {"name": name}
        return fn

    tasks = [
        Task(id="a", fn=make_fn("a")),
        Task(id="b", fn=make_fn("b"), depends_on=["a"]),
        Task(id="c", fn=make_fn("c"), depends_on=["a"]),
        Task(id="d", fn=make_fn("d"), depends_on=["b", "c"]),
    ]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()
    metrics = orchestrator.run(graph, ctx)

    assert set(calls) == {"a", "b", "c", "d"}
    assert calls.index("a") < calls.index("b")
    assert calls.index("a") < calls.index("c")
    assert calls.index("b") < calls.index("d")
    assert calls.index("c") < calls.index("d")
    assert metrics.success_rate == 1.0
    assert ctx.output_of("d") == {"name": "d"}


def test_bounded_retry_succeeds_before_exhausting_attempts():
    attempts = {"count": 0}

    def flaky(ctx):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient failure")
        return {"ok": True}

    tasks = [Task(id="flaky", fn=flaky, max_retries=3)]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()
    metrics = orchestrator.run(graph, ctx)

    assert attempts["count"] == 3
    assert metrics.success_rate == 1.0
    assert metrics.retry_count == 2
    assert ctx.output_of("flaky") == {"ok": True}


def test_retries_exhausted_triggers_rollback_and_safe_stop():
    rollback_called = []

    def always_fails(ctx):
        raise RuntimeError("permanent failure")

    def rollback(ctx):
        rollback_called.append(True)

    tasks = [Task(id="broken", fn=always_fails, max_retries=2, rollback_fn=rollback, critical=True)]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()

    with pytest.raises(SafeStopTriggered) as exc_info:
        orchestrator.run(graph, ctx)

    assert exc_info.value.task_id == "broken"
    assert rollback_called == [True]


def test_non_critical_task_failure_does_not_stop_pipeline():
    def always_fails(ctx):
        raise RuntimeError("non-critical failure")

    def downstream(ctx):
        return {"ran": True}

    tasks = [
        Task(id="optional", fn=always_fails, max_retries=0, critical=False),
        Task(id="downstream", fn=downstream, depends_on=["optional"]),
    ]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()
    # Should NOT raise, even though "optional" failed - downstream still gets
    # scheduled since safe-stop only triggers for critical tasks.
    orchestrator.run(graph, ctx)


def test_automated_exit_gate_blocks_and_is_retried():
    calls = {"count": 0}

    def fn(ctx):
        calls["count"] += 1
        return {"value": calls["count"]}

    gate = AutomatedGate(
        "min_value", lambda ctx: ctx.output_of("gated")["value"] >= 2, "value too low"
    )
    tasks = [Task(id="gated", fn=fn, max_retries=3, exit_gates=[gate])]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()
    metrics = orchestrator.run(graph, ctx)

    assert calls["count"] == 2  # failed gate on attempt 1, passed on attempt 2
    assert metrics.success_rate == 1.0


def test_human_approval_gate_approved_continues():
    tasks = [
        Task(
            id="gate_task",
            fn=lambda ctx: {},
            entry_gates=[HumanApprovalGate("approve", auto_approve_provider)],
        ),
        Task(id="after", fn=lambda ctx: {"ran": True}, depends_on=["gate_task"]),
    ]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()
    orchestrator.run(graph, ctx)
    assert ctx.output_of("after") == {"ran": True}


def test_human_approval_gate_rejected_safe_stops():
    tasks = [
        Task(
            id="gate_task", fn=lambda ctx: {},
            entry_gates=[HumanApprovalGate("approve", auto_reject_provider)],
            critical=True,
        ),
    ]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()
    with pytest.raises(SafeStopTriggered):
        orchestrator.run(graph, ctx)


def test_dynamic_replanning_reruns_downstream_tasks():
    run_count = {"a": 0, "b": 0, "c": 0}

    def task_a(ctx):
        run_count["a"] += 1
        replan = ctx.inputs.get("trigger_replan_on_run", 0) == run_count["a"]
        return {"value": run_count["a"], "replan": replan}

    def task_b(ctx):
        run_count["b"] += 1
        return {"value": run_count["b"]}

    def task_c(ctx):
        run_count["c"] += 1
        return {"value": run_count["c"]}

    tasks = [
        Task(id="a", fn=task_a),
        Task(id="b", fn=task_b, depends_on=["a"]),
        Task(id="c", fn=task_c, depends_on=["b"]),
    ]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx(trigger_replan_on_run=1)  # "a" signals replan=True on its first run

    orchestrator.run(graph, ctx)

    assert run_count["a"] == 1
    # b and c should have been re-run automatically due to the replan signal
    assert run_count["b"] == 2
    assert run_count["c"] == 2
    replan_events = [e for e in ctx.history if e.event == "replan_triggered"]
    assert len(replan_events) == 1


def test_dirty_task_reruns_itself_and_downstream():
    """Distinct from stale_tasks: an externally-triggered 'dirty' task (e.g. a
    human edited its input) must re-run ITSELF too, not just its downstream."""
    run_count = {"a": 0, "b": 0}

    def task_a(ctx):
        run_count["a"] += 1
        return {"value": run_count["a"]}

    def task_b(ctx):
        run_count["b"] += 1
        return {"value": run_count["b"]}

    tasks = [Task(id="a", fn=task_a), Task(id="b", fn=task_b, depends_on=["a"])]
    graph = TaskGraph(tasks)
    orchestrator = Orchestrator()
    ctx = _ctx()

    orchestrator.run(graph, ctx)
    assert run_count == {"a": 1, "b": 1}

    ctx.dirty_tasks.add("a")
    orchestrator.run(graph, ctx)
    assert run_count == {"a": 2, "b": 2}  # both re-ran, unlike the stale_tasks case
