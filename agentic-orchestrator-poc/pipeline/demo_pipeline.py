"""
Wires the SDLC agent functions (pipeline/sdlc_agents.py) into an explicit
dependency graph with entry/exit gates - this is the "URL shortener SDLC"
scenario being orchestrated, per the assignment brief.

Graph shape (see docs/architecture.md for the diagram):

    requirements_analysis
            |
    architecture_design
        /        \\
  implementation  documentation      <- genuinely parallel (fan-out)
        |
   test_writing                      <- depends only on implementation
        \\        |        /
            quality_gate             <- fan-in / synchronization point
                 |
            human_approval           <- governance checkpoint
                 |
            release_readiness
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from orchestrator.context import PipelineContext
from orchestrator.gates import AutomatedGate, Gate, HumanApprovalGate
from orchestrator.graph import TaskGraph
from orchestrator.task import Task
from pipeline import sdlc_agents as agents
from pipeline.sdlc_agents import slugify


def _rollback_implementation(ctx: PipelineContext) -> None:
    """
    Real rollback, not a no-op: `implementation` writes its artifact file
    BEFORE its simulated-failure check can raise, so a failed/exhausted
    attempt can leave a partial file on disk. This deletes it, restoring
    the workspace to a clean state - demonstrating an actual rollback
    action, not just a hook that exists for show.
    """
    requirements = ctx.output_of("requirements_analysis") or {"raw_request": ""}
    fn_name = f"feature_{slugify(requirements['raw_request'])}"
    partial_file = Path(ctx.inputs["workspace_dir"]) / f"{fn_name}.py"
    if partial_file.exists():
        partial_file.unlink()
        ctx.record("implementation", "rollback_action", f"Deleted partial artifact {partial_file}")


def _files_exist_gate(name: str, ctx_key: str, file_key: str) -> Gate:
    def predicate(ctx: PipelineContext) -> bool:
        output = ctx.output_of(ctx_key)
        return output is not None and Path(output[file_key]).exists()

    return AutomatedGate(name, predicate, reason_on_fail=f"{ctx_key}.{file_key} was not produced")


def _quality_gate() -> Gate:
    def predicate(ctx: PipelineContext) -> bool:
        impl = ctx.output_of("implementation")
        tests = ctx.output_of("test_writing")
        docs = ctx.output_of("documentation")
        if not (impl and tests and docs):
            return False
        impl_ok = Path(impl["file"]).exists()
        test_ok = "def test_" in Path(tests["file"]).read_text(encoding="utf-8")
        docs_ok = len(Path(docs["file"]).read_text(encoding="utf-8").strip()) > 0
        return impl_ok and test_ok and docs_ok

    return AutomatedGate(
        "quality_gate", predicate, reason_on_fail="implementation/tests/docs failed validation"
    )


def build_pipeline(approval_provider: Callable[[PipelineContext, str], bool]) -> TaskGraph:
    tasks = [
        Task(
            id="requirements_analysis",
            fn=agents.requirements_analysis,
            depends_on=[],
            description="Interpret intent, flag ambiguity, normalize into a structured "
            "requirement.",
        ),
        Task(
            id="architecture_design",
            fn=agents.architecture_design,
            depends_on=["requirements_analysis"],
            description="Identify impacted modules/symbols; produce an implementation plan.",
        ),
        Task(
            id="implementation",
            fn=agents.implementation,
            depends_on=["architecture_design"],
            max_retries=2,
            retry_backoff_seconds=0.1,
            rollback_fn=_rollback_implementation,
            description="Generate the implementation artifact.",
        ),
        Task(
            id="documentation",
            fn=agents.documentation,
            depends_on=["architecture_design"],
            description="Generate documentation - runs in parallel with implementation.",
        ),
        Task(
            id="test_writing",
            fn=agents.test_writing,
            depends_on=["implementation"],
            entry_gates=[_files_exist_gate("implementation_exists", "implementation", "file")],
            description="Generate tests for the implementation artifact.",
        ),
        Task(
            id="quality_gate",
            fn=lambda ctx: {"checked": True},
            depends_on=["implementation", "test_writing", "documentation"],
            exit_gates=[_quality_gate()],
            description="Synchronization point: validate all parallel outputs together.",
        ),
        Task(
            id="human_approval",
            fn=lambda ctx: {"checkpoint": "release"},
            depends_on=["quality_gate"],
            entry_gates=[HumanApprovalGate("release_approval", approval_provider)],
            description="Human approval checkpoint before release.",
        ),
        Task(
            id="release_readiness",
            fn=agents.release_readiness,
            depends_on=["human_approval"],
            description="Final release-readiness artifact.",
        ),
    ]
    return TaskGraph(tasks)
