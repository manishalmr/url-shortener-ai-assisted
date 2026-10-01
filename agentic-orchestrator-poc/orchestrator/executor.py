"""
The orchestrator: executes a TaskGraph with governance.

Requirements being satisfied here (see docs/architecture.md for the full
mapping): non-linear stateful execution with governance; sequential +
parallel paths with synchronization; bounded retries, fallback/rollback,
and safe-stop controls; dynamic re-planning when upstream outputs change.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from orchestrator.context import PipelineContext
from orchestrator.gates import HumanApprovalGate
from orchestrator.graph import TaskGraph
from orchestrator.observability import AuditLog, RunMetrics
from orchestrator.task import Task

TaskOutcome = str  # "success" | "failed_stopped" | "skipped"


class SafeStopTriggered(Exception):
    """Raised when a critical task exhausts its bounded retries."""

    def __init__(self, task_id: str, reason: str):
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"Safe-stop triggered by task '{task_id}': {reason}")


class Orchestrator:
    def __init__(self, audit_log: AuditLog | None = None, max_replan_cycles: int = 3):
        self.audit_log = audit_log or AuditLog()
        self.max_replan_cycles = max_replan_cycles

    def run(self, graph: TaskGraph, ctx: PipelineContext) -> RunMetrics:
        """
        Executes the graph to completion. Safe to call more than once on the
        SAME ctx (e.g. after a caller edits ctx.inputs and marks a task
        dirty/stale) - ctx.completed_tasks persists across calls, so a second
        call only re-executes the affected subset, not the whole graph.
        """
        metrics = RunMetrics(run_id=ctx.run_id, started_at=time.time())
        completed = ctx.completed_tasks

        self._execute_batches(graph, ctx, graph.execution_batches(), completed, metrics)

        replan_cycles = 0
        while (ctx.stale_tasks or ctx.dirty_tasks) and replan_cycles < self.max_replan_cycles:
            replan_cycles += 1
            downstream_only = set(ctx.stale_tasks)
            include_self = set(ctx.dirty_tasks)
            ctx.stale_tasks.clear()
            ctx.dirty_tasks.clear()

            affected: set[str] = set(include_self)
            for tid in downstream_only | include_self:
                affected |= graph.downstream_of(tid)
            affected &= set(graph.all_task_ids())

            if not affected:
                continue

            triggered_by = downstream_only | include_self
            ctx.record(
                "orchestrator", "replan_triggered",
                f"Upstream change in {sorted(triggered_by)} -> re-running {sorted(affected)}",
            )
            self.audit_log.emit(
                ctx.run_id,
                "orchestrator",
                "replan_triggered",
                f"triggered_by={sorted(triggered_by)} "
                f"affected={sorted(affected)} cycle={replan_cycles}",
            )
            completed -= affected

            sub_batches = [
                [tid for tid in batch if tid in affected] for batch in graph.execution_batches()
            ]
            sub_batches = [b for b in sub_batches if b]
            self._execute_batches(graph, ctx, sub_batches, completed, metrics)

        metrics.finish()
        return metrics

    # ------------------------------------------------------------------

    def _execute_batches(
        self,
        graph: TaskGraph,
        ctx: PipelineContext,
        batches: list[list[str]],
        completed: set[str],
        metrics: RunMetrics,
    ) -> None:
        for batch in batches:
            pending = [tid for tid in batch if tid not in completed]
            if not pending:
                continue

            with ThreadPoolExecutor(max_workers=max(1, len(pending))) as pool:
                futures = {
                    pool.submit(self._run_single_task, graph.get(tid), ctx, metrics): tid
                    for tid in pending
                }
                stop_reason: tuple[str, str] | None = None
                for future in as_completed(futures):
                    tid = futures[future]
                    outcome = future.result()
                    if outcome == "success":
                        completed.add(tid)
                    elif outcome == "failed_stopped":
                        stop_reason = (tid, "critical task exhausted retries")

            if stop_reason is not None:
                task_id, reason = stop_reason
                self.audit_log.emit(ctx.run_id, "orchestrator", "safe_stop", reason)
                ctx.record("orchestrator", "safe_stop", f"Halted by '{task_id}': {reason}")
                raise SafeStopTriggered(task_id, reason)

    def _run_single_task(
        self, task: Task, ctx: PipelineContext, metrics: RunMetrics
    ) -> TaskOutcome:
        for gate in task.entry_gates:
            result = gate.check(ctx)
            self.audit_log.emit(
                ctx.run_id, task.id, "entry_gate",
                f"{gate.name}={result.passed} ({result.reason})",
            )
            ctx.record(task.id, "entry_gate", f"{gate.name}: {result.reason}")
            if not result.passed:
                if isinstance(gate, HumanApprovalGate):
                    return "failed_stopped" if task.critical else "skipped"
                return "failed_stopped" if task.critical else "skipped"

        last_error = ""
        attempt_number = 0
        while attempt_number <= task.max_retries:
            attempt_number += 1
            attempt = metrics.new_attempt(task.id, attempt_number)
            try:
                result = task.fn(ctx)
                ctx.set_output(task.id, result)

                exit_ok = True
                for gate in task.exit_gates:
                    gr = gate.check(ctx)
                    self.audit_log.emit(
                        ctx.run_id, task.id, "exit_gate",
                        f"{gate.name}={gr.passed} ({gr.reason})",
                    )
                    ctx.record(task.id, "exit_gate", f"{gate.name}: {gr.reason}")
                    if not gr.passed:
                        exit_ok = False
                        last_error = gr.reason
                        break

                if exit_ok:
                    attempt.outcome = "success"
                    attempt.ended_at = time.time()
                    self.audit_log.emit(
                        ctx.run_id, task.id, "task_success", f"attempt={attempt_number}"
                    )

                    if isinstance(result, dict) and result.get("replan"):
                        ctx.stale_tasks.add(task.id)
                        reason = result.get("replan_reason", "upstream output changed")
                        ctx.record(task.id, "replan_signal", reason)
                        self.audit_log.emit(ctx.run_id, task.id, "replan_signal", reason)

                    return "success"

                attempt.outcome = "failed"
                attempt.ended_at = time.time()
            except Exception as exc:  # noqa: BLE001 - orchestrator must not crash on task errors
                last_error = str(exc)
                attempt.outcome = "failed"
                attempt.ended_at = time.time()
                ctx.record(task.id, "task_exception", last_error)
                self.audit_log.emit(ctx.run_id, task.id, "task_exception", last_error)

            if attempt_number <= task.max_retries:
                self.audit_log.emit(
                    ctx.run_id, task.id, "retry",
                    f"attempt {attempt_number} failed ({last_error}); retrying",
                )
                if task.retry_backoff_seconds:
                    time.sleep(task.retry_backoff_seconds)

        # Retries exhausted.
        ctx.record(task.id, "retries_exhausted", last_error)
        self.audit_log.emit(ctx.run_id, task.id, "retries_exhausted", last_error)

        if task.rollback_fn is not None:
            try:
                task.rollback_fn(ctx)
                rollback_attempt = metrics.new_attempt(task.id, attempt_number + 1)
                rollback_attempt.outcome = "rolled_back"
                rollback_attempt.ended_at = time.time()
                self.audit_log.emit(ctx.run_id, task.id, "rollback", "rollback_fn executed")
                ctx.record(task.id, "rollback", "rollback_fn executed")
            except Exception as exc:  # noqa: BLE001
                self.audit_log.emit(ctx.run_id, task.id, "rollback_failed", str(exc))
                ctx.record(task.id, "rollback_failed", str(exc))

        return "failed_stopped" if task.critical else "skipped"
