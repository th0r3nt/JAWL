import pytest
from unittest.mock import MagicMock
from src.l0_state.interfaces.host.os_state import HostOSState
from src.utils.event.bus import EventBus
from src.l2_interfaces.host.os.events import HostOSEvents
from src.l2_interfaces.host.os.skills.monitoring import HostOSMonitoring


def test_os_events_update_telemetry(os_client):
    state = HostOSState()
    bus = EventBus()
    events = HostOSEvents(os_client, state, bus)

    # Обращаемся к поллеру напрямую
    events.telemetry._update_telemetry()

    assert "CPU:" in state.telemetry
    assert "RAM:" in state.telemetry
    assert "Топ процессов (RAM):" in state.telemetry
    assert len(state.telemetry) > 20


def test_os_events_check_sandbox_tree(os_client):
    state = HostOSState()
    bus = EventBus()
    events = HostOSEvents(os_client, state, bus)

    folder_a = os_client.sandbox_dir / "folder_a"
    folder_a.mkdir()
    (folder_a / "file1.txt").touch()
    (os_client.sandbox_dir / "root_file.log").touch()

    # Обращаемся к поллеру файлов
    events.files._update_file_trees()

    assert "sandbox/" in state.sandbox_files
    assert "folder_a" in state.sandbox_files
    assert "file1.txt" in state.sandbox_files
    assert "root_file.log" in state.sandbox_files
    assert "├──" in state.sandbox_files or "└──" in state.sandbox_files


@pytest.mark.asyncio
async def test_os_monitoring_track_and_untrack(os_client):
    events_mock = MagicMock(spec=HostOSEvents)
    events_mock._watches = {}
    events_mock.track_path.return_value = True
    events_mock.untrack_path.return_value = True

    monitoring = HostOSMonitoring(os_client, events_mock)

    res_track = await monitoring.track_directory(str(os_client.sandbox_dir))
    assert res_track.is_success is True
    events_mock.track_path.assert_called_once()

    res_untrack = await monitoring.untrack_directory(str(os_client.sandbox_dir))
    assert res_untrack.is_success is True
    events_mock.untrack_path.assert_called_once()
