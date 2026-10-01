from pathlib import Path

from orchestrator.context import PipelineContext
from orchestrator.executor import Orchestrator, SafeStopTriggered
from orchestrator.gates import auto_approve_provider, auto_reject_provider
from pipeline.demo_pipeline import build_pipeline


def _ctx(tmp_path: Path, **extra_inputs) -> PipelineContext:
    return PipelineContext(
        run_id="itest",
        inputs={
            "feature_request": "Add a function that reverses a given string",
            "workspace_dir": str(tmp_path / "workspace"),
            **extra_inputs,
        },
    )


def test_greenfield_pipeline_runs_end_to_end(tmp_path):
    graph = build_pipeline(auto_approve_provider)
    ctx = _ctx(tmp_path)
    orchestrator = Orchestrator()
    metrics = orchestrator.run(graph, ctx)

    assert metrics.success_rate == 1.0
    impl = ctx.output_of("implementation")
    tests = ctx.output_of("test_writing")
    docs = ctx.output_of("documentation")
    release = ctx.output_of("release_readiness")

    assert Path(impl["file"]).exists()
    assert Path(tests["file"]).exists()
    assert Path(docs["file"]).exists()
    assert release["released"] is True
    assert Path(release["notes_file"]).exists()


def test_brownfield_codebase_reasoning_finds_impacted_symbols(tmp_path):
    sample = Path(__file__).parent.parent / "pipeline" / "sample_target" / "existing_module.py"
    graph = build_pipeline(auto_approve_provider)
    ctx = _ctx(tmp_path, existing_module_path=str(sample))
    Orchestrator().run(graph, ctx)

    arch = ctx.output_of("architecture_design")
    assert set(arch["impacted_symbols"]) == {"greet", "add"}
    assert arch["brownfield"] is True


def test_brownfield_bounded_retry_recovers(tmp_path):
    graph = build_pipeline(auto_approve_provider)
    ctx = _ctx(tmp_path, _fail_implementation_times=2)
    metrics = Orchestrator().run(graph, ctx)

    assert metrics.success_rate == 1.0
    assert metrics.retry_count >= 2


def test_brownfield_permanent_failure_safe_stops_and_rolls_back(tmp_path):
    graph = build_pipeline(auto_approve_provider)
    ctx = _ctx(tmp_path, _force_fail_implementation=True)
    orchestrator = Orchestrator()

    try:
        orchestrator.run(graph, ctx)
        raise AssertionError("expected SafeStopTriggered")
    except SafeStopTriggered as exc:
        assert exc.task_id == "implementation"

    rollback_events = [e for e in ctx.history if e.event == "rollback"]
    assert len(rollback_events) == 1
    # release_readiness must never have run - no partial release.
    assert ctx.output_of("release_readiness") is None


def test_ambiguous_requirement_flags_ambiguity_and_records_assumptions(tmp_path):
    graph = build_pipeline(auto_approve_provider)
    ctx = _ctx(tmp_path, feature_request="make it better")
    Orchestrator().run(graph, ctx)

    reqs = ctx.output_of("requirements_analysis")
    assert reqs["is_ambiguous"] is True
    assert len(reqs["assumptions"]) > 0


def test_ambiguous_requirement_clarification_triggers_replan(tmp_path):
    graph = build_pipeline(auto_approve_provider)
    ctx = _ctx(tmp_path, feature_request="make it better")
    orchestrator = Orchestrator()
    orchestrator.run(graph, ctx)
    assert ctx.output_of("requirements_analysis")["is_ambiguous"] is True

    ctx.inputs["feature_request"] = "Add a function that reverses a given string"
    ctx.dirty_tasks.add("requirements_analysis")
    orchestrator.run(graph, ctx)

    assert ctx.output_of("requirements_analysis")["is_ambiguous"] is False
    replan_events = [e for e in ctx.history if e.event == "replan_triggered"]
    assert len(replan_events) == 1


def test_human_approval_rejection_prevents_release(tmp_path):
    graph = build_pipeline(auto_reject_provider)
    ctx = _ctx(tmp_path)
    orchestrator = Orchestrator()

    try:
        orchestrator.run(graph, ctx)
        raise AssertionError("expected SafeStopTriggered")
    except SafeStopTriggered:
        pass

    assert ctx.output_of("release_readiness") is None
