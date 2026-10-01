"""
Audit-grade observability and reliability metrics.

Requirement being satisfied: "provide audit-grade observability and
traceability, track reliability metrics such as success rate, retry/rollback
frequency, MTTR, and end-to-end latency."
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TaskAttempt:
    task_id: str
    attempt_number: int
    started_at: float
    ended_at: float | None = None
    outcome: str = "running"  # running | success | failed | rolled_back | skipped
    detail: str = ""

    @property
    def duration_seconds(self) -> float:
        if self.ended_at is None:
            return 0.0
        return self.ended_at - self.started_at


@dataclass
class RunMetrics:
    run_id: str
    started_at: float
    ended_at: float | None = None
    attempts: list[TaskAttempt] = field(default_factory=list)

    def new_attempt(self, task_id: str, attempt_number: int) -> TaskAttempt:
        attempt = TaskAttempt(
            task_id=task_id, attempt_number=attempt_number, started_at=time.time()
        )
        self.attempts.append(attempt)
        return attempt

    def finish(self) -> None:
        self.ended_at = time.time()

    # --- Reliability metrics -------------------------------------------------

    @property
    def total_latency_seconds(self) -> float:
        if self.ended_at is None:
            return 0.0
        return self.ended_at - self.started_at

    @property
    def success_rate(self) -> float:
        """Fraction of DISTINCT tasks that eventually succeeded (not attempt-level)."""
        by_task: dict[str, list[TaskAttempt]] = {}
        for a in self.attempts:
            by_task.setdefault(a.task_id, []).append(a)
        if not by_task:
            return 1.0
        succeeded = sum(
            1 for attempts in by_task.values() if any(a.outcome == "success" for a in attempts)
        )
        return succeeded / len(by_task)

    @property
    def retry_count(self) -> int:
        return sum(1 for a in self.attempts if a.attempt_number > 1)

    @property
    def retry_frequency(self) -> float:
        """Retries per distinct task attempted."""
        by_task = {a.task_id for a in self.attempts}
        if not by_task:
            return 0.0
        return self.retry_count / len(by_task)

    @property
    def rollback_count(self) -> int:
        return sum(1 for a in self.attempts if a.outcome == "rolled_back")

    @property
    def mttr_seconds(self) -> float:
        """
        Mean time to recovery: for each task that failed at least once before
        eventually succeeding, the time between its FIRST failed attempt
        starting and its eventually-successful attempt ending. Averaged
        across all such tasks; 0.0 if nothing ever failed-then-recovered.
        """
        by_task: dict[str, list[TaskAttempt]] = {}
        for a in self.attempts:
            by_task.setdefault(a.task_id, []).append(a)

        recoveries = []
        for attempts in by_task.values():
            attempts_sorted = sorted(attempts, key=lambda a: a.attempt_number)
            first_failure = next((a for a in attempts_sorted if a.outcome == "failed"), None)
            success = next((a for a in attempts_sorted if a.outcome == "success"), None)
            if first_failure and success and success.ended_at:
                recoveries.append(success.ended_at - first_failure.started_at)

        if not recoveries:
            return 0.0
        return sum(recoveries) / len(recoveries)

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_latency_seconds": round(self.total_latency_seconds, 3),
            "success_rate": round(self.success_rate, 3),
            "retry_count": self.retry_count,
            "retry_frequency": round(self.retry_frequency, 3),
            "rollback_count": self.rollback_count,
            "mttr_seconds": round(self.mttr_seconds, 3),
            "total_attempts": len(self.attempts),
            "distinct_tasks": len({a.task_id for a in self.attempts}),
        }


class AuditLog:
    """Append-only structured event log - the 'audit-grade traceability' artifact."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self._events: list[dict] = []

    def emit(self, run_id: str, task_id: str, event: str, detail: str = "") -> None:
        record = {
            "timestamp": time.time(),
            "run_id": run_id,
            "task_id": task_id,
            "event": event,
            "detail": detail,
        }
        self._events.append(record)
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    @property
    def events(self) -> list[dict]:
        return list(self._events)


def metrics_to_dict(metrics: RunMetrics) -> dict:
    return {
        "run_id": metrics.run_id,
        "summary": metrics.summary(),
        "attempts": [asdict(a) for a in metrics.attempts],
    }
