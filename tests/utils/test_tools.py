from src.utils import _tools


def test_is_agent_running_removes_stale_pid_file(tmp_path, monkeypatch):
    pid_file = tmp_path / "agent.pid"
    pid_file.write_text("999999999")

    monkeypatch.setattr(_tools, "get_pid_file_path", lambda: pid_file)
    monkeypatch.setattr(_tools.psutil, "pid_exists", lambda _pid: False)

    assert _tools.is_agent_running() is False
    assert not pid_file.exists()
