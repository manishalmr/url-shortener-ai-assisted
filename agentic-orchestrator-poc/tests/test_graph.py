import pytest

from orchestrator.graph import CycleError, TaskGraph, UnknownDependencyError
from orchestrator.task import Task


def _noop(ctx):
    return {}


def test_execution_batches_orders_by_dependency():
    tasks = [
        Task(id="a", fn=_noop),
        Task(id="b", fn=_noop, depends_on=["a"]),
        Task(id="c", fn=_noop, depends_on=["a"]),
        Task(id="d", fn=_noop, depends_on=["b", "c"]),
    ]
    graph = TaskGraph(tasks)
    batches = graph.execution_batches()
    assert batches == [["a"], ["b", "c"], ["d"]]


def test_independent_tasks_are_a_single_batch():
    tasks = [Task(id="x", fn=_noop), Task(id="y", fn=_noop)]
    graph = TaskGraph(tasks)
    assert graph.execution_batches() == [["x", "y"]]


def test_cycle_detected():
    tasks = [
        Task(id="a", fn=_noop, depends_on=["b"]),
        Task(id="b", fn=_noop, depends_on=["a"]),
    ]
    with pytest.raises(CycleError):
        TaskGraph(tasks)


def test_unknown_dependency_detected():
    tasks = [Task(id="a", fn=_noop, depends_on=["ghost"])]
    with pytest.raises(UnknownDependencyError):
        TaskGraph(tasks)


def test_downstream_of_transitive():
    tasks = [
        Task(id="a", fn=_noop),
        Task(id="b", fn=_noop, depends_on=["a"]),
        Task(id="c", fn=_noop, depends_on=["b"]),
        Task(id="unrelated", fn=_noop),
    ]
    graph = TaskGraph(tasks)
    assert graph.downstream_of("a") == {"b", "c"}
    assert graph.downstream_of("unrelated") == set()
