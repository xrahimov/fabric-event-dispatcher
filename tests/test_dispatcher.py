from datetime import timedelta

from conftest import FakeJobs

from fabric_dispatcher import RequestStore, Route, chain_next, run_pass, should_chain

ROUTES = {"refresh": Route("ws", "pipe-refresh"), "publish": Route("ws", "pipe-publish")}


def status(conn, rid):
    return conn.execute("SELECT status FROM dispatch_request WHERE id = ?", (rid,)).fetchone()[0]


def test_claim_is_won_once(conn, add):
    rid = add(conn)
    a, b = RequestStore(conn), RequestStore(conn)
    assert a.claim(rid) is True
    assert b.claim(rid) is False


def test_pending_request_starts_its_pipeline(conn, add):
    rid = add(conn)
    jobs = FakeJobs()
    result = run_pass(RequestStore(conn), jobs, ROUTES)
    assert result.started == [rid]
    assert jobs.starts[0][:2] == ("pipe-refresh", "Pipeline")
    assert status(conn, rid) == "running"
    assert result.open_work is True


def test_start_failure_marks_request_failed(conn, add):
    rid = add(conn)
    result = run_pass(RequestStore(conn), FakeJobs(start_code=429), ROUTES)
    assert result.failed == [rid]
    assert status(conn, rid) == "failed"


def test_unknown_action_fails(conn, add):
    rid = add(conn, action="nope")
    run_pass(RequestStore(conn), FakeJobs(), ROUTES)
    assert status(conn, rid) == "failed"


def test_finished_job_triggers_follow_up_then_work_closes(conn, add):
    rid = add(conn, status="running", url="u1")
    jobs = FakeJobs(instance_status={"u1": "Completed"})
    follow_ups = []

    def on_finished(store, request_id):
        follow_ups.append(request_id)

    result = run_pass(RequestStore(conn), jobs, ROUTES, on_finished)
    assert result.finished == [rid] and follow_ups == [rid]
    assert status(conn, rid) == "succeeded"
    assert result.open_work is False


def test_stale_requests_do_not_keep_chain_alive(conn, add):
    add(conn, age=timedelta(hours=25))
    store = RequestStore(conn)
    assert store.pending() == []
    assert store.open_work_exists() is False


def test_unapplied_setting_is_open_work(conn):
    conn.execute("INSERT INTO dispatch_setting (name, desired_value) VALUES ('paused', '1')")
    assert RequestStore(conn).open_work_exists() is True
    conn.execute("UPDATE dispatch_setting SET actual_value = '1'")
    assert RequestStore(conn).open_work_exists() is False


def test_should_chain_respects_cap():
    assert should_chain(True, 0, 240)
    assert not should_chain(True, 239, 240)
    assert not should_chain(False, 0, 240)


def test_chain_passes_every_parameter_forward():
    jobs = FakeJobs()
    params = {"max_chain_depth": 240, "sql_server": "srv"}
    assert chain_next(jobs, "ws", "nb", params, chain_depth=3)
    item, job_type, sent = jobs.starts[0]
    assert (item, job_type) == ("nb", "RunNotebook")
    assert sent == {"max_chain_depth": 240, "sql_server": "srv", "chain_depth": 4}
