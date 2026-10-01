"""
Explicit dependency graph with topological batching.

Requirement being satisfied: "an explicit dependency graph with entry/exit
gates, support sequential and parallel paths with synchronization" -
`execution_batches()` groups tasks into levels; all tasks in the same level
have no dependency on each other and can run in parallel, while each level
only starts after the previous level's tasks have all completed (the
synchronization point / fan-in).
"""
from __future__ import annotations

from orchestrator.task import Task


class CycleError(Exception):
    pass


class UnknownDependencyError(Exception):
    pass


class TaskGraph:
    def __init__(self, tasks: list[Task]):
        self._tasks: dict[str, Task] = {t.id: t for t in tasks}
        self._validate()

    def _validate(self) -> None:
        for task in self._tasks.values():
            for dep in task.depends_on:
                if dep not in self._tasks:
                    raise UnknownDependencyError(
                        f"Task '{task.id}' depends on unknown task '{dep}'"
                    )
        self.execution_batches()  # raises CycleError if the graph has a cycle

    def get(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def all_task_ids(self) -> list[str]:
        return list(self._tasks.keys())

    def downstream_of(self, task_id: str) -> set[str]:
        """All tasks (transitively) that depend on `task_id`, directly or indirectly."""
        downstream: set[str] = set()
        changed = True
        while changed:
            changed = False
            for t in self._tasks.values():
                if t.id in downstream:
                    continue
                if any(dep == task_id or dep in downstream for dep in t.depends_on):
                    downstream.add(t.id)
                    changed = True
        return downstream

    def execution_batches(self) -> list[list[str]]:
        """
        Kahn's algorithm topological sort, grouped into parallel-eligible
        batches (levels). Raises CycleError if the graph isn't a DAG.
        """
        remaining = {tid: set(t.depends_on) for tid, t in self._tasks.items()}
        batches: list[list[str]] = []

        while remaining:
            ready = sorted([tid for tid, deps in remaining.items() if not deps])
            if not ready:
                raise CycleError(
                    f"Cycle detected among remaining tasks: {sorted(remaining.keys())}"
                )
            batches.append(ready)
            for tid in ready:
                del remaining[tid]
            for deps in remaining.values():
                deps.difference_update(ready)

        return batches
