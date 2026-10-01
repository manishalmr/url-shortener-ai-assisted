"""
Entry/exit gates and the human-approval checkpoint.

Requirement being satisfied: "explicit dependency graph with entry/exit
gates ... enforce human approval checkpoints for high-impact actions."
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.context import PipelineContext


@dataclass
class GateResult:
    passed: bool
    reason: str


class Gate:
    name: str = "gate"

    def check(self, ctx: PipelineContext) -> GateResult:  # pragma: no cover - interface
        raise NotImplementedError


class AutomatedGate(Gate):
    """Wraps a plain predicate function as a gate (e.g. 'tests passed', 'lint clean')."""

    def __init__(
        self, name: str, predicate: Callable[[PipelineContext], bool], reason_on_fail: str
    ):
        self.name = name
        self._predicate = predicate
        self._reason_on_fail = reason_on_fail

    def check(self, ctx: PipelineContext) -> GateResult:
        passed = self._predicate(ctx)
        return GateResult(passed=passed, reason="ok" if passed else self._reason_on_fail)


class HumanApprovalGate(Gate):
    """
    Pauses the pipeline for a human decision on a high-impact action.

    PoC implementation: approval state is held in-memory on the gate instance
    and driven by an `ApprovalProvider` callback so both the CLI demo
    (interactive `input()`) and the automated test suite (pre-programmed
    yes/no) can drive it without changing orchestrator code.
    """

    def __init__(self, name: str, approval_provider: Callable[[PipelineContext, str], bool]):
        self.name = name
        self._approval_provider = approval_provider

    def check(self, ctx: PipelineContext) -> GateResult:
        approved = self._approval_provider(ctx, self.name)
        return GateResult(
            passed=approved,
            reason="approved by human reviewer" if approved else "rejected by human reviewer",
        )


def cli_approval_provider(ctx: PipelineContext, checkpoint_name: str) -> bool:
    """Interactive approval used by the CLI demo runner."""
    print(f"\n[HUMAN APPROVAL REQUIRED] Checkpoint: {checkpoint_name}")
    print(f"  Run: {ctx.run_id}")
    print(f"  Outputs so far: {list(ctx.outputs.keys())}")
    answer = input("  Approve to continue? [y/N]: ").strip().lower()
    return answer == "y"


def auto_approve_provider(_ctx: PipelineContext, _checkpoint_name: str) -> bool:
    """Non-interactive approval used by automated tests / unattended demo runs."""
    return True


def auto_reject_provider(_ctx: PipelineContext, _checkpoint_name: str) -> bool:
    return False
