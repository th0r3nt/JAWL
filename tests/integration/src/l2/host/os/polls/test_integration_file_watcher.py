import pytest
from pathlib import Path

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.polls.file_watcher import FileWatcher


@pytest.mark.asyncio
async def test_integration_file_watcher_generates_diff(tmp_path: Path):
    """
    Интеграционный тест: "Изменение файла на диске -> Генерация Diff -> Обновление L0 State".
    Проверяет, что когда файл меняется (например, другим субагентом или юзером),
    система корректно вычисляет разницу и выводит её на приборную панель.
    """

    # 1. Поднимаем клиент и стейт
    config = HostOSConfig(access_level=HostOSAccessLevel.SANDBOX, file_diff_max_chars=500)
    state = HostOSState()
    client = HostOSClient(base_dir=tmp_path, config=config, state=state, timezone=3)

    bus = EventBus()
    watcher = FileWatcher(client=client, state=state, bus=bus)

    # Чтобы не ждать реальных событий от ОС, мы вручную инициируем методы,
    # которые вызываются обработчиком Watchdog

    target_file = client.sandbox_dir / "config.txt"

    # 2. Имитируем создание файла
    target_file.write_text("server=127.0.0.1\nport=80", encoding="utf-8")

    # Пробрасываем событие создания
    await watcher.handle_file_system_event(Events.HOST_OS_FILE_CREATED, str(target_file))
    await watcher._process_batch()  # Принудительно обрабатываем очередь

    # Файл должен закешироваться
    assert str(target_file) in watcher._file_cache

    # 3. Имитируем изменение файла (поменяли порт и добавили пароль)
    target_file.write_text("server=127.0.0.1\nport=443\npassword=secret", encoding="utf-8")

    # Пробрасываем событие изменения
    await watcher.handle_file_system_event(Events.HOST_OS_FILE_MODIFIED, str(target_file))
    await watcher._process_batch()

    # 4. Проверяем, что Diff сгенерирован и попал в стейт агента
    assert len(state.recent_file_changes) == 1
    diff_block = state.recent_file_changes[0]

    # В Diff-блоке должны быть видны git-подобные изменения
    assert "-port=80" in diff_block
    assert "+port=443" in diff_block
    assert "+password=secret" in diff_block
    assert "config.txt" in diff_block

    # 5. Убеждаемся, что провайдер контекста отдает этот Diff
    context_str = await client.get_context_block()
    assert "Recent Changes in Files:" in context_str
    assert "+port=443" in context_str
