from conftest import FakeJobs

from fabric_dispatcher import FabricJobs, WakeTarget, wake
from fabric_dispatcher.jobs import to_job_parameters

TARGET = WakeTarget("ws", "nb")


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, get=None, post=None):
        self._get, self._post = get, post
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._get

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self._post


def test_is_active_reads_instance_states():
    s = FakeSession(get=FakeResponse(body={"value": [{"status": "Completed"}, {"status": "InProgress"}]}))
    assert FabricJobs(lambda: "t", s).is_active("ws", "nb") is True
    _, url, kw = s.calls[0]
    assert url.endswith("/workspaces/ws/items/nb/jobs/instances")
    assert kw["headers"]["Authorization"] == "Bearer t"


def test_start_counts_only_202_as_started():
    ok = FakeSession(post=FakeResponse(202, headers={"Location": "https://x/1"}))
    res = FabricJobs(lambda: "t", ok).start("ws", "nb", "RunNotebook", {"chain_depth": 1})
    assert res.started and res.instance_url == "https://x/1"
    _, _, kw = ok.calls[0]
    assert kw["params"] == {"jobType": "RunNotebook"}
    assert kw["json"]["executionData"]["parameters"]["chain_depth"] == {"value": 1, "type": "int"}

    busy = FakeSession(post=FakeResponse(200))
    assert FabricJobs(lambda: "t", busy).start("ws", "nb", "RunNotebook").started is False


def test_parameter_types():
    assert to_job_parameters({"a": True, "b": 2, "c": 1.5, "d": "x"}) == {
        "a": {"value": True, "type": "bool"},
        "b": {"value": 2, "type": "int"},
        "c": {"value": 1.5, "type": "float"},
        "d": {"value": "x", "type": "string"},
    }


def test_wake_skips_when_running():
    jobs = FakeJobs(active=True)
    assert wake(jobs, TARGET).outcome == "already_running"
    assert jobs.starts == []


def test_wake_starts_dispatcher():
    jobs = FakeJobs()
    assert wake(jobs, TARGET, "user saved").outcome == "started"
    assert jobs.starts[0][:2] == ("nb", "RunNotebook")


def test_wake_never_raises():
    assert wake(FakeJobs(active=RuntimeError("401")), TARGET).outcome == "failed"
    assert wake(FakeJobs(start_code=403), TARGET).outcome == "failed"
