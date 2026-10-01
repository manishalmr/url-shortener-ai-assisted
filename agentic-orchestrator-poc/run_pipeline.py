#!/usr/bin/env python
"""
CLI demo runner - drives the orchestrator through the three required
scenarios (greenfield / brownfield / ambiguous). See README.md for usage
and docs/scenarios.md for the full narrative behind each one.
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

from orchestrator.context import PipelineContext
from orchestrator.executor import Orchestrator, SafeStopTriggered
from orchestrator.gates import auto_approve_provider, cli_approval_provider
from orchestrator.observability import AuditLog
from pipeline.demo_pipeline import build_pipeline

ROOT = Path(__file__).parent
SAMPLE_TARGET = ROOT / "pipeline" / "sample_target" / "existing_module.py"


def _fresh_workspace(run_id: str) -> Path:
    workspace = ROOT / "pipeline" / "workspace" / run_id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _print_summary(ctx: PipelineContext, metrics, audit_log: AuditLog) -> None:
    print("\n" + "=" * 70)
    print(f"RUN COMPLETE: {ctx.run_id}")
    print("=" * 70)
    print("\n--- Decision lineage (ctx.history) ---")
    for entry in ctx.history:
        print(f"  [{entry.task_id}] {entry.event}: {entry.detail}")
    print("\n--- Reliability metrics ---")
    print(json.dumps(metrics.summary(), indent=2))
    print(f"\n--- Audit log: {len(audit_log.events)} events recorded ---")


def run_greenfield(interactive: bool) -> None:
    run_id = f"greenfield-{uuid.uuid4().hex[:8]}"
    workspace = _fresh_workspace(run_id)
    audit_log = AuditLog(path=workspace / "audit_log.jsonl")
    approval = cli_approval_provider if interactive else auto_approve_provider

    ctx = PipelineContext(
        run_id=run_id,
        inputs={
            "feature_request": "Add an endpoint that reverses a given string",
            "workspace_dir": str(workspace),
        },
    )
    graph = build_pipeline(approval)
    orchestrator = Orchestrator(audit_log=audit_log)
    metrics = orchestrator.run(graph, ctx)
    _print_summary(ctx, metrics, audit_log)


def run_brownfield(interactive: bool, fail_times: int, force_fail: bool) -> None:
    run_id = f"brownfield-{uuid.uuid4().hex[:8]}"
    workspace = _fresh_workspace(run_id)
    audit_log = AuditLog(path=workspace / "audit_log.jsonl")
    approval = cli_approval_provider if interactive else auto_approve_provider

    ctx = PipelineContext(
        run_id=run_id,
        inputs={
            "feature_request": "Extend existing_module with a subtract capability",
            "workspace_dir": str(workspace),
            "existing_module_path": str(SAMPLE_TARGET),
            "_fail_implementation_times": fail_times,
            "_force_fail_implementation": force_fail,
        },
    )
    graph = build_pipeline(approval)
    orchestrator = Orchestrator(audit_log=audit_log)
    try:
        metrics = orchestrator.run(graph, ctx)
        _print_summary(ctx, metrics, audit_log)
    except SafeStopTriggered as exc:
        print(f"\n*** SAFE-STOP TRIGGERED: {exc} ***")
        print("Pipeline halted safely - no partial release occurred.")
        print(json.dumps([e for e in audit_log.events if e["event"] in
                          ("retry", "retries_exhausted", "rollback", "safe_stop")], indent=2))


def run_ambiguous(interactive: bool) -> None:
    run_id = f"ambiguous-{uuid.uuid4().hex[:8]}"
    workspace = _fresh_workspace(run_id)
    audit_log = AuditLog(path=workspace / "audit_log.jsonl")
    approval = cli_approval_provider if interactive else auto_approve_provider

    ctx = PipelineContext(
        run_id=run_id,
        inputs={
            "feature_request": "make it better",  # deliberately vague
            "workspace_dir": str(workspace),
            "_requirements_revision": 1,
        },
    )
    graph = build_pipeline(approval)
    orchestrator = Orchestrator(audit_log=audit_log)
    orchestrator.run(graph, ctx)

    print("\n--- Initial (ambiguous) run ---")
    print(f"Ambiguity detected: {ctx.output_of('requirements_analysis')['is_ambiguous']}")
    print(f"Assumptions made: {ctx.output_of('requirements_analysis')['assumptions']}")

    # Simulate a stakeholder clarifying the requirement mid-flight.
    print("\n--- Stakeholder clarifies the requirement; triggering dynamic re-plan ---")
    ctx.inputs["feature_request"] = "Add a function that reverses a given string"
    ctx.inputs["_requirements_revision"] = 2
    ctx.dirty_tasks.add("requirements_analysis")
    ctx.record("orchestrator", "manual_replan_trigger", "Stakeholder clarified the requirement")

    metrics2 = orchestrator.run(graph, ctx)
    is_ambiguous_now = ctx.output_of("requirements_analysis")["is_ambiguous"]
    print(f"Ambiguity after clarification: {is_ambiguous_now}")
    _print_summary(ctx, metrics2, audit_log)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic orchestrator PoC demo runner")
    parser.add_argument(
        "--scenario", choices=["greenfield", "brownfield", "ambiguous"], required=True
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Prompt for real human approval via CLI input()"
    )
    parser.add_argument(
        "--fail-implementation-times", type=int, default=0,
        help="[brownfield] Make 'implementation' fail this many times before succeeding",
    )
    parser.add_argument(
        "--force-fail-implementation", action="store_true",
        help=(
            "[brownfield] Make 'implementation' always fail -> "
            "exhausts retries -> rollback -> safe-stop"
        ),
    )
    args = parser.parse_args()

    if args.scenario == "greenfield":
        run_greenfield(args.interactive)
    elif args.scenario == "brownfield":
        run_brownfield(
            args.interactive, args.fail_implementation_times, args.force_fail_implementation
        )
    elif args.scenario == "ambiguous":
        run_ambiguous(args.interactive)


if __name__ == "__main__":
    main()
