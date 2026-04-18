import os
import pytest
from pathlib import Path

from src.utils.settings import HostOSConfig
from src.utils.event.bus import EventBus

from src.l0_state.interfaces.state import HostOSState

from src.l2_interfaces.host.os.events import HostOSEvents
from src.l2_interfaces.host.os.client import HostOSClient, MadnessLevel
from src.l2_interfaces.host.os.skills.files import HostOSFiles
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.system import HostOSSystem
from src.l2_interfaces.host.os.skills.network import HostOSNetwork


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def os_client(tmp_path: Path):
    """
    Создает изолированного клиента ПК с уровнем VOYEUR (1).
    Передает временную директорию tmp_path напрямую как корень фреймворка.
    """
    config = HostOSConfig(
        enabled=True,
        madness_level=1,
        env_access=False,
        monitoring_interval_sec=20,
        execution_timeout_sec=60,
        file_read_max_chars=3000,
        file_list_limit=100,
        http_response_max_chars=1000,
        top_processes_limit=10,
    )
    state = HostOSState()
    client = HostOSClient(base_dir=tmp_path, config=config, state=state, timezone=3)
    return client


# ===================================================================
# TESTS: PCClient
# ===================================================================


def test_gatekeeper_cage(os_client):
    """Тест CAGE (0): доступ строго только в sandbox/."""
    os_client.madness_level = MadnessLevel.CAGE

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"

    # Внутри песочницы - ОК
    assert os_client.validate_path(safe_path) == safe_path.resolve()

    # Чтение фреймворка - Запрещено
    with pytest.raises(PermissionError, match="CAGE"):
        os_client.validate_path(framework_path, is_write=False)


def test_gatekeeper_voyeur(os_client):
    """Тест VOYEUR (1): чтение фреймворка, запись только в sandbox/."""
    os_client.madness_level = MadnessLevel.VOYEUR

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"
    os_path = Path("/etc/passwd") if os.name != "nt" else Path("C:/Windows/System32/config")

    # Запись в песочнице - ОК
    assert os_client.validate_path(safe_path, is_write=True) == safe_path.resolve()

    # Запись во фреймворке - Запрещено
    with pytest.raises(PermissionError, match="VOYEUR"):
        os_client.validate_path(framework_path, is_write=True)

    # Чтение фреймворка - ОК
    assert os_client.validate_path(framework_path, is_write=False) == framework_path.resolve()

    # Чтение чужой системы - Запрещено
    with pytest.raises(PermissionError, match="VOYEUR"):
        os_client.validate_path(os_path, is_write=False)


def test_gatekeeper_env_protection(os_client):
    """Тест: запрет доступа к .env файлам работает даже в режиме GOD_MODE."""
    os_client.madness_level = MadnessLevel.GOD_MODE
    os_client.config.env_access = False

    secret_path = os_client.framework_dir / ".env"
    dev_secret_path = os_client.framework_dir / "config" / ".env.dev"

    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(secret_path, is_write=False)

    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(dev_secret_path, is_write=True)


# ===================================================================
# TESTS: PCFiles
# ===================================================================


@pytest.mark.asyncio
async def test_os_files_write_and_read(os_client):
    """Тест: запись файла в песочницу и его чтение."""
    files = HostOSFiles(os_client)
    filepath = str(os_client.sandbox_dir / "hello.txt")

    # Пишем
    res_write = await files.write_file(filepath, "Hello World", mode="w")
    assert res_write.is_success is True

    # Читаем
    res_read = await files.read_file(filepath)
    assert res_read.is_success is True
    assert "Hello World" in res_read.message


@pytest.mark.asyncio
async def test_os_files_delete_out_of_bounds(os_client):
    """Тест: агент не должен иметь возможности удалять файлы вне песочницы на 1 уровне."""
    files = HostOSFiles(os_client)
    forbidden_path = str(os_client.framework_dir / "main.py")

    res_del = await files.delete_file(forbidden_path)
    assert res_del.is_success is False
    assert "VOYEUR: Запись разрешена строго в папке" in res_del.message


@pytest.mark.asyncio
async def test_os_files_delete_directory(os_client):
    """Тест: успешное рекурсивное удаление папки."""
    files = HostOSFiles(os_client)

    # Создаем папку и файл внутри
    target_dir = os_client.sandbox_dir / "target_folder"
    target_dir.mkdir()
    (target_dir / "inner_file.txt").touch()

    # Удаляем
    res = await files.delete_directory(str(target_dir))

    assert res.is_success is True
    assert not target_dir.exists()


@pytest.mark.asyncio
async def test_os_files_delete_directory_root_protection(os_client):
    """Тест: попытка удалить корень песочницы или фреймворка блокируется."""
    files = HostOSFiles(os_client)

    # Пытаемся снести всю песочницу
    res = await files.delete_directory(str(os_client.sandbox_dir))

    assert res.is_success is False
    assert "Запрещено удалять корневую директорию" in res.message
    assert os_client.sandbox_dir.exists()  # Папка должна выжить


@pytest.mark.asyncio
async def test_os_files_create_directories(os_client):
    """Тест: массовое создание вложенных директорий."""
    files = HostOSFiles(os_client)

    # Передаем два пути. Один простой, второй вложенный
    paths = [
        str(os_client.sandbox_dir / "docs"),
        str(os_client.sandbox_dir / "src" / "api" / "v1"),
    ]

    res = await files.create_directories(paths)

    assert res.is_success is True
    assert (os_client.sandbox_dir / "docs").exists()
    assert (os_client.sandbox_dir / "src" / "api" / "v1").exists()
    assert "Успешно созданы директории: docs, v1" in res.message


# ===================================================================
# TESTS: PCExecution
# ===================================================================


@pytest.mark.asyncio
async def test_execute_shell_command_safe(os_client):
    """Тест: выполнение простой безопасной кроссплатформенной команды."""
    os_client.madness_level = MadnessLevel.SURGEON  # Требуется для shell_command
    executor = HostOSExecution(os_client)

    # Используем python -c, так как это работает везде (Windows, Linux, Mac)
    res = await executor.execute_shell_command("python -c \"print('Agent Online')\"")

    assert res.is_success is True
    assert "Agent Online" in res.message
    assert "Команда завершилась с кодом 0" in res.message


# ===================================================================
# TESTS: PCSystem
# ===================================================================


@pytest.mark.asyncio
async def test_get_telemetry(os_client):
    """Тест: получение телеметрии ОС."""
    sys_skill = HostOSSystem(os_client)
    res = await sys_skill.get_telemetry()

    assert res.is_success is True
    assert "CPU" in res.message
    assert "RAM" in res.message
    assert "Uptime" in res.message


# ===================================================================
# TESTS: PCNetwork
# ===================================================================


@pytest.mark.asyncio
async def test_ping_localhost(os_client):
    """Тест: успешный пинг локалхоста."""
    net = HostOSNetwork(os_client)
    res = await net.ping_host("127.0.0.1", count=1)

    assert res.is_success is True
    assert "доступен" in res.message


@pytest.mark.asyncio
async def test_check_closed_port(os_client):
    """Тест: проверка заведомо закрытого порта должна корректно возвращать Fail без краша."""
    net = HostOSNetwork(os_client)
    # Используем случайный порт, который вряд ли открыт
    res = await net.check_port("127.0.0.1", 54321, timeout=1)

    assert res.is_success is False
    # Либо таймаут, либо ConnectionRefused
    assert "отказано" in res.message or "Таймаут" in res.message


# ===================================================================
# TESTS: PCEvents (Monitoring & State)
# ===================================================================


def test_os_events_update_telemetry(os_client):
    """Тест: сбор телеметрии успешно записывается в state (включая процессы)."""
    state = HostOSState()
    bus = EventBus()
    events = HostOSEvents(os_client, state, bus)

    # Вызываем синхронный метод обновления
    events._update_telemetry()

    assert "CPU:" in state.telemetry
    assert "RAM:" in state.telemetry
    assert "Топ процессов (RAM):" in state.telemetry
    # Убедимся, что процесс хотя бы один есть (даже в тестовой среде должен быть запущен python/pytest)
    assert len(state.telemetry) > 20


def test_os_events_check_sandbox_tree(os_client):
    """Тест: построение ASCII-дерева файлов песочницы."""
    state = HostOSState()
    bus = EventBus()
    events = HostOSEvents(os_client, state, bus)

    # Имитируем создание файлов
    folder_a = os_client.sandbox_dir / "folder_a"
    folder_a.mkdir()
    (folder_a / "file1.txt").touch()
    (os_client.sandbox_dir / "root_file.log").touch()

    # Запускаем проверку
    events._check_sandbox()

    # Проверяем наличие ключевых элементов ASCII-дерева в стейте
    assert "sandbox/" in state.sandbox_files
    assert "folder_a" in state.sandbox_files
    assert "file1.txt" in state.sandbox_files
    assert "root_file.log" in state.sandbox_files

    # Проверяем символы соединителей
    assert "├──" in state.sandbox_files or "└──" in state.sandbox_files
