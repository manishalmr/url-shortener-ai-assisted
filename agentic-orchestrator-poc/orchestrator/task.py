"""
Task definition for the orchestration graph.

Design note (see docs/limitations.md for the full scoping rationale): each
Task's `fn` is a plain, deterministic Python callable representing one SDLC
stage (requirements, design, implementation, ...). This PoC does NOT wire
real LLM calls into every stage - that's flagged as a documented, deliberate
simplification given the time-box. The orchestration mechanics around these
tasks (graph execution, gates, retries, rollback, replanning, observability)
ARE fully real and tested - that's the part this PoC exists to demonstrate.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from orchestrator.gates import Gate

if TYPE_CHECKING:
    from orchestrator.context import PipelineContext

TaskFn = Callable[["PipelineContext"], dict[str, Any]]


@dataclass
class Task:
    id: str
    fn: TaskFn
    depends_on: list[str] = field(default_factory=list)
    entry_gates: list[Gate] = field(default_factory=list)
    exit_gates: list[Gate] = field(default_factory=list)
    max_retries: int = 0
    retry_backoff_seconds: float = 0.0
    critical: bool = True  # if True, exhausted retries triggers a safe-stop of the whole run
    rollback_fn: TaskFn | None = None
    description: str = ""
