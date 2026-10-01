"""
Cross-stage context and decision lineage.

Requirement being satisfied: "preserve cross-stage context and decision
lineage" - every task's output is stored keyed by task id, AND every
meaningful decision (gate pass/fail, retry, rollback, replan trigger) is
appended to `history` with a reason, so the full "why did the pipeline do
X" story can be reconstructed after the fact.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LineageEntry:
    timestamp: float
    task_id: str
    event: str
    detail: str


@dataclass
class PipelineContext:
    run_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    history: list[LineageEntry] = field(default_factory=list)
    stale_tasks: set[str] = field(default_factory=set)
    """Self-signaled replanning: a task's OWN result said 'my downstream
    consumers need to be recomputed' (e.g. result={"replan": True}). The
    signaling task itself is NOT re-run - only everything downstream of it."""
    dirty_tasks: set[str] = field(default_factory=set)
    """Externally-triggered replanning: something outside normal execution
    (e.g. a human edited ctx.inputs) marked a task's OWN inputs as changed.
    That task itself IS re-run, plus everything downstream of it."""
    completed_tasks: set[str] = field(default_factory=set)
    """Persists ACROSS multiple Orchestrator.run(graph, ctx) calls on the same
    context - this is what makes 'run once, change an input, run again' only
    re-execute the affected subset instead of the whole graph from scratch."""
    scratch: dict[str, Any] = field(default_factory=dict)
    """Transient bookkeeping (e.g. demo failure-injection counters) - distinct
    from `outputs`, which is the official per-task result registry."""

    def record(self, task_id: str, event: str, detail: str = "") -> None:
        self.history.append(
            LineageEntry(timestamp=time.time(), task_id=task_id, event=event, detail=detail)
        )

    def output_of(self, task_id: str) -> Any:
        return self.outputs.get(task_id)

    def set_output(self, task_id: str, value: Any) -> None:
        self.outputs[task_id] = value
