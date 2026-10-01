import time

from orchestrator.observability import AuditLog, RunMetrics


def test_success_rate_counts_distinct_tasks():
    m = RunMetrics(run_id="r1", started_at=time.time())
    a1 = m.new_attempt("a", 1)
    a1.outcome = "success"
    a1.ended_at = time.time()
    b1 = m.new_attempt("b", 1)
    b1.outcome = "failed"
    b1.ended_at = time.time()
    b2 = m.new_attempt("b", 2)
    b2.outcome = "success"
    b2.ended_at = time.time()

    assert m.success_rate == 1.0  # both "a" and "b" eventually succeeded
    assert m.retry_count == 1  # b's attempt 2 counts as a retry
    assert m.retry_frequency == 0.5  # 1 retry / 2 distinct tasks


def test_success_rate_with_a_permanent_failure():
    m = RunMetrics(run_id="r1", started_at=time.time())
    a1 = m.new_attempt("a", 1)
    a1.outcome = "failed"
    a1.ended_at = time.time()

    assert m.success_rate == 0.0


def test_rollback_count():
    m = RunMetrics(run_id="r1", started_at=time.time())
    m.new_attempt("a", 1).outcome = "failed"
    rollback_attempt = m.new_attempt("a", 2)
    rollback_attempt.outcome = "rolled_back"

    assert m.rollback_count == 1


def test_mttr_measures_failure_to_recovery():
    m = RunMetrics(run_id="r1", started_at=time.time())
    t0 = time.time()
    fail = m.new_attempt("a", 1)
    fail.started_at = t0
    fail.ended_at = t0 + 1
    fail.outcome = "failed"

    success = m.new_attempt("a", 2)
    success.started_at = t0 + 1
    success.ended_at = t0 + 3
    success.outcome = "success"

    assert m.mttr_seconds == 3  # success.ended_at - fail.started_at = (t0+3) - t0


def test_mttr_zero_when_nothing_ever_failed():
    m = RunMetrics(run_id="r1", started_at=time.time())
    ok = m.new_attempt("a", 1)
    ok.outcome = "success"
    ok.ended_at = time.time()
    assert m.mttr_seconds == 0.0


def test_summary_contains_expected_keys():
    m = RunMetrics(run_id="r1", started_at=time.time())
    m.finish()
    summary = m.summary()
    for key in (
        "run_id", "total_latency_seconds", "success_rate", "retry_count",
        "retry_frequency", "rollback_count", "mttr_seconds", "total_attempts", "distinct_tasks",
    ):
        assert key in summary


def test_audit_log_records_events_in_memory():
    log = AuditLog()
    log.emit("run1", "task_a", "task_success", "attempt=1")
    assert len(log.events) == 1
    assert log.events[0]["task_id"] == "task_a"
    assert log.events[0]["event"] == "task_success"


def test_audit_log_writes_to_file(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path=path)
    log.emit("run1", "task_a", "task_success", "attempt=1")
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
