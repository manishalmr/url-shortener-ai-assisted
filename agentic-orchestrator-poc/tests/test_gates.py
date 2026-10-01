from orchestrator.context import PipelineContext
from orchestrator.gates import (
    AutomatedGate,
    HumanApprovalGate,
    auto_approve_provider,
    auto_reject_provider,
)


def _ctx():
    return PipelineContext(run_id="r1")


def test_automated_gate_pass():
    gate = AutomatedGate("always_true", lambda ctx: True, "should not see this")
    result = gate.check(_ctx())
    assert result.passed is True
    assert result.reason == "ok"


def test_automated_gate_fail_reason():
    gate = AutomatedGate("always_false", lambda ctx: False, "custom failure reason")
    result = gate.check(_ctx())
    assert result.passed is False
    assert result.reason == "custom failure reason"


def test_human_approval_gate_uses_provider():
    approve_gate = HumanApprovalGate("checkpoint", auto_approve_provider)
    reject_gate = HumanApprovalGate("checkpoint", auto_reject_provider)

    assert approve_gate.check(_ctx()).passed is True
    assert reject_gate.check(_ctx()).passed is False
