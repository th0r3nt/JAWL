import pytest
from unittest.mock import MagicMock, AsyncMock
from src.utils.event.registry import Events
from src.l2_interfaces.host.os.polls.file_watcher import FileWatcher


@pytest.mark.asyncio
async def test_file_watcher_diff_generation(os_client):
    """Тест: генерация diff-а и сохранение в памяти."""
    bus_mock = MagicMock()
    bus_mock.publish = AsyncMock()
    
    watcher = FileWatcher(os_client, os_client.state, bus_mock)
    
    test_file = os_client.sandbox_dir / "diff_test.txt"
    
    # 1. Создание файла
    test_file.write_text("Line 1\nLine 2\n", encoding="utf-8")
    await watcher._publish_single_file_event(str(test_file), Events.HOST_OS_FILE_CREATED)
    
    assert str(test_file) in watcher._file_cache
    
    # 2. Модификация файла
    test_file.write_text("Line 1\nLine 2 changed\nLine 3\n", encoding="utf-8")
    await watcher._publish_single_file_event(str(test_file), Events.HOST_OS_FILE_MODIFIED)
    
    # Проверяем, что Diff упал в кэш
    assert len(os_client.state.recent_file_changes) == 1
    diff_str = os_client.state.recent_file_changes[0]
    
    assert "-Line 2" in diff_str
    assert "+Line 2 changed" in diff_str
    assert "+Line 3" in diff_str