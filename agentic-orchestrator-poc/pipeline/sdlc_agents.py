"""
The SDLC "agents" being orchestrated - one function per pipeline stage.

Scoping note (full rationale in docs/limitations.md): these are deterministic
Python functions, not live LLM calls. They do REAL, verifiable work (parse
requirements text, inspect an existing file, write real implementation/test/
doc files to a workspace, validate them) so the orchestration mechanics
around them - gating, retries, rollback, replanning, observability - are
exercised against genuine task outcomes rather than hardcoded "always
succeeds" stubs. Wiring real LLM calls into each stage is the natural next
step and is called out explicitly as future work.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from orchestrator.context import PipelineContext
from orchestrator.policy import scan_code_for_policy_violations

AMBIGUITY_MARKERS = ["better", "improve", "nicer", "somehow", "etc", "and so on"]


def requirements_analysis(ctx: PipelineContext) -> dict[str, Any]:
    raw_request: str = ctx.inputs["feature_request"]
    is_ambiguous = any(marker in raw_request.lower() for marker in AMBIGUITY_MARKERS) or len(
        raw_request.split()
    ) < 4

    assumptions = []
    if is_ambiguous:
        assumptions = [
            "Interpreting the vague request as: add a small, additive utility function "
            "rather than a breaking change.",
            "No UI/API contract changes assumed unless explicitly stated.",
        ]

    normalized = {
        "raw_request": raw_request,
        "is_ambiguous": is_ambiguous,
        "assumptions": assumptions,
        "revision": ctx.inputs.get("_requirements_revision", 1),
    }
    return normalized


def architecture_design(ctx: PipelineContext) -> dict[str, Any]:
    requirements = ctx.output_of("requirements_analysis")
    target_file: str | None = ctx.inputs.get("existing_module_path")

    impacted_symbols: list[str] = []
    if target_file and Path(target_file).exists():
        content = Path(target_file).read_text(encoding="utf-8")
        impacted_symbols = re.findall(r"^def\s+(\w+)", content, flags=re.MULTILINE)

    return {
        "plan": f"Add one new function addressing: {requirements['raw_request']!r}",
        "impacted_symbols": impacted_symbols,
        "brownfield": bool(impacted_symbols),
    }


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "feature"


def implementation(ctx: PipelineContext) -> dict[str, Any]:
    workspace = Path(ctx.inputs["workspace_dir"])
    workspace.mkdir(parents=True, exist_ok=True)

    requirements = ctx.output_of("requirements_analysis")
    slug = slugify(requirements["raw_request"])
    fn_name = f"feature_{slug}"

    code = (
        f'def {fn_name}(payload: str) -> str:\n'
        f'    """Generated for request: {requirements["raw_request"]!r}"""\n'
        f'    return f"processed: {{payload}}"\n'
    )

    violations = scan_code_for_policy_violations(code)
    if violations:
        raise RuntimeError(f"Policy guardrail rejected generated code: {violations}")

    impl_path = workspace / f"{fn_name}.py"
    impl_path.write_text(code, encoding="utf-8")

    # --- Deterministic, controllable failure injection for the demo -----
    # Two independently controllable behaviors, both driven by CLI flags in
    # run_pipeline.py, so the retry-succeeds path and the
    # retries-exhausted -> rollback -> safe-stop path can each be shown
    # on demand rather than relying on real, non-reproducible flakiness.
    ctx.scratch["implementation_attempts"] = ctx.scratch.get("implementation_attempts", 0) + 1
    attempt_num = ctx.scratch["implementation_attempts"]

    if ctx.inputs.get("_force_fail_implementation"):
        raise RuntimeError(
            "Simulated PERSISTENT implementation failure "
            "(demo of retries-exhausted -> rollback -> safe-stop)"
        )
    fail_times = ctx.inputs.get("_fail_implementation_times", 0)
    if attempt_num <= fail_times:
        raise RuntimeError(
            f"Simulated TRANSIENT implementation failure on attempt {attempt_num} "
            "(demo of bounded retries succeeding)"
        )

    return {"function_name": fn_name, "file": str(impl_path)}


def test_writing(ctx: PipelineContext) -> dict[str, Any]:
    workspace = Path(ctx.inputs["workspace_dir"])
    workspace.mkdir(parents=True, exist_ok=True)

    impl = ctx.output_of("implementation")
    fn_name = impl["function_name"]

    test_code = (
        f"from {fn_name} import {fn_name}\n\n\n"
        f"def test_{fn_name}():\n"
        f'    assert {fn_name}("x") == "processed: x"\n'
    )
    test_path = workspace / f"test_{fn_name}.py"
    test_path.write_text(test_code, encoding="utf-8")
    return {"file": str(test_path)}


def documentation(ctx: PipelineContext) -> dict[str, Any]:
    """
    Deliberately depends only on requirements/architecture output (NOT on
    `implementation`'s output) even though it derives the same function name
    independently via the same slug logic - this keeps it genuinely
    parallel-eligible with `implementation` in the graph (see
    pipeline/demo_pipeline.py), rather than secretly serializing behind it.
    """
    workspace = Path(ctx.inputs["workspace_dir"])
    workspace.mkdir(parents=True, exist_ok=True)

    requirements = ctx.output_of("requirements_analysis")
    fn_name = f"feature_{slugify(requirements['raw_request'])}"

    doc = (
        f"# {fn_name}\n\n"
        f"Addresses: {requirements['raw_request']}\n\n"
        f"Assumptions:\n"
        + "".join(f"- {a}\n" for a in requirements["assumptions"])
    )
    doc_path = workspace / f"{fn_name}.md"
    doc_path.write_text(doc, encoding="utf-8")
    return {"file": str(doc_path)}


def release_readiness(ctx: PipelineContext) -> dict[str, Any]:
    workspace = Path(ctx.inputs["workspace_dir"])
    impl = ctx.output_of("implementation")
    notes_path = workspace / "RELEASE_NOTES.md"
    notes_path.write_text(
        f"# Release notes\n\nShipped: {impl['function_name']} (see {impl['file']})\n",
        encoding="utf-8",
    )
    return {"released": True, "notes_file": str(notes_path)}
