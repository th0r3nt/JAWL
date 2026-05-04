import os
import shutil
import pytest
from unittest.mock import patch

from src.l2_interfaces.host.os.client import HostOSAccessLevel
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.decorators import require_access
from src.l3_agent.skills.registry import SkillResult
from src.utils._tools import get_project_root


class DummyOSClass:
    def __init__(self, host_os_client):
        self.host_os = host_os_client

    @require_access(HostOSAccessLevel.OPERATOR)
    async def dangerous_action(self):
        return SkillResult.ok("Бум! Я удалил базу!")


@pytest.mark.asyncio
async def test_execute_shell_command_safe(os_client):
    """Тест: выполнение простой безопасной кроссплатформенной команды."""
    os_client.access_level = HostOSAccessLevel.ROOT  # Требуется для shell_command
    executor = HostOSExecution(os_client)

    # Используем python -c, так как это работает везде (Windows, Linux, Mac)
    res = await executor.execute_shell_command("python -c \"print('Agent Online')\"")

    assert res.is_success is True
    assert "Agent Online" in res.message
    assert "Команда завершилась с кодом 0" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.execution.psutil.Process")
async def test_execution_kill_process_not_found(mock_process, os_client):
    """Тест: Агент пытается убить процесс, которого не существует."""
    import psutil

    os_client.access_level = HostOSAccessLevel.ROOT
    executor = HostOSExecution(os_client)

    mock_process.side_effect = psutil.NoSuchProcess(pid=99999)

    res = await executor.kill_process(pid=99999)
    assert res.is_success is False
    assert "не найден" in res.message


@pytest.mark.asyncio
async def test_require_access_decorator_blocks(os_client):
    """Тест: Декоратор блокирует выполнение, если Access Level ниже требуемого."""
    dummy = DummyOSClass(os_client)
    res = await dummy.dangerous_action()

    assert res.is_success is False
    assert "Отказано в доступе" in res.message


@pytest.mark.asyncio
async def test_require_os_access_decorator_allows(os_client):
    """Тест: Декоратор пропускает выполнение, если Access Level достаточный."""
    os_client.access_level = HostOSAccessLevel.ROOT
    dummy = DummyOSClass(os_client)

    res = await dummy.dangerous_action()
    assert res.is_success is True


def test_build_isolated_env_scrubs_secrets(os_client):
    """Тест: Сборщик окружения вырезает секретные ключи, чтобы изолированный скрипт не мог их прочитать."""
    executor = HostOSExecution(os_client)

    # Добавляем фейковые секреты в системный env
    os.environ["SECRET_TEST_TOKEN"] = "12345"
    os.environ["LLM_API_KEY_1"] = "sk-xxx"
    os.environ["NORMAL_VAR"] = "ok_value"

    env = executor._build_isolated_env()

    assert "SECRET_TEST_TOKEN" not in env
    assert "LLM_API_KEY_1" not in env
    assert "NORMAL_VAR" in env

    # Чистим за собой
    del os.environ["SECRET_TEST_TOKEN"]
    del os.environ["LLM_API_KEY_1"]
    del os.environ["NORMAL_VAR"]


@pytest.mark.asyncio
async def test_sandbox_guard_blocks_traversal_and_subprocess(os_client, tmp_path):
    """
    Интеграционный тест: Защита Sandbox Guard при запуске python-скриптов.
    Мы копируем обертку sandbox_runner.py, пишем вредоносный скрипт и убеждаемся,
    что он падает с PermissionError при попытке взлома системы изнутри подпроцесса.
    """
    os_client.access_level = HostOSAccessLevel.OBSERVER
    executor = HostOSExecution(os_client)

    # 1. Подготавливаем среду: копируем реальный sandbox_runner из исходников во временную папку
    real_root = get_project_root()
    template_src = real_root / "src" / "utils" / "templates" / "sandbox_runner.py"

    template_dst = tmp_path / "src" / "utils" / "templates" / "sandbox_runner.py"
    template_dst.parent.mkdir(parents=True, exist_ok=True)

    if template_src.exists():
        shutil.copy2(template_src, template_dst)
    else:
        pytest.skip("Файл sandbox_runner.py не найден в исходниках. Тест пропущен.")

    # Создаем фейковый .env файл вне песочницы
    secret_file = tmp_path / ".env"
    secret_file.write_text("SUPER_SECRET_KEY=123", encoding="utf-8")

    # 2. Пишем вредоносный скрипт
    malicious_code = """
import os
import subprocess

try:
    # Пытаемся прочитать файл вне песочницы (Path Traversal)
    with open("../.env", "r") as f:
        print(f"LEAKED: {f.read()}")
except PermissionError as e:
    print(f"OPEN_BLOCKED: {e}")

try:
    # Пытаемся выйти в Shell (Shell Escape)
    subprocess.check_output("echo 1", shell=True)
    print("SUBPROCESS_WORKED")
except PermissionError as e:
    print(f"SUBPROCESS_BLOCKED: {e}")
"""
    malicious_script = os_client.sandbox_dir / "evil.py"
    malicious_script.write_text(malicious_code, encoding="utf-8")

    # 3. Выполняем скрипт через скилл
    res = await executor.execute_script("sandbox/evil.py")

    # Скрипт должен выполниться (код 0), но внутри него исключения должны быть перехвачены
    assert res.is_success is True, res.message

    # 4. Проверяем STDOUT скрипта: Гард должен был отловить попытки и выкинуть PermissionError
    assert "LEAKED: SUPER_SECRET_KEY=123" not in res.message
    assert "OPEN_BLOCKED:" in res.message
    assert "Path Traversal попытка заблокирована" in res.message

    assert "SUBPROCESS_WORKED" not in res.message
    assert "SUBPROCESS_BLOCKED:" in res.message
    assert "Использование shell/subprocess заблокировано" in res.message


@pytest.mark.asyncio
async def test_sandbox_guard_blocks_os_spawn_and_exec_family(os_client, tmp_path):
    """
    Раньше Sandbox Guard перезаписывал только subprocess.Popen/run/check_output/call
    и os.system/os.popen. Обход: os.spawnlp / os.posix_spawn / os.execvp /
    os.fork вызывают процесс напрямую через syscall, мимо всего списка.
    """
    os_client.access_level = HostOSAccessLevel.OBSERVER
    executor = HostOSExecution(os_client)

    real_root = get_project_root()
    template_src = real_root / "src" / "utils" / "templates" / "sandbox_runner.py"
    template_dst = tmp_path / "src" / "utils" / "templates" / "sandbox_runner.py"
    template_dst.parent.mkdir(parents=True, exist_ok=True)

    if template_src.exists():
        shutil.copy2(template_src, template_dst)
    else:
        pytest.skip("Файл sandbox_runner.py не найден в исходниках. Тест пропущен.")

    malicious_code = """
import os

# 1. os.spawnlp — раньше совсем не блокировался
try:
    os.spawnlp(os.P_WAIT, 'echo', 'echo', 'SPAWN_WORKED')
    print("SPAWNLP_NOT_BLOCKED")
except PermissionError as e:
    print(f"SPAWNLP_BLOCKED: {e}")
except Exception as e:
    print(f"SPAWNLP_ERROR: {type(e).__name__}")

# 2. os.posix_spawn — прямой syscall
try:
    os.posix_spawn('/bin/echo', ['echo', 'POSIX_WORKED'], os.environ)
    print("POSIX_SPAWN_NOT_BLOCKED")
except PermissionError as e:
    print(f"POSIX_SPAWN_BLOCKED: {e}")
except Exception as e:
    print(f"POSIX_SPAWN_ERROR: {type(e).__name__}")

# 3. os.execvp — замена текущего процесса; тестируем что хотя бы обёртка падает
try:
    os.execvp('echo', ['echo', 'EXEC_WORKED'])
    print("EXECVP_NOT_BLOCKED")
except PermissionError as e:
    print(f"EXECVP_BLOCKED: {e}")
except Exception as e:
    print(f"EXECVP_ERROR: {type(e).__name__}")

# 4. os.fork
try:
    pid = os.fork()
    if pid == 0:
        # child
        os._exit(0)
    print("FORK_NOT_BLOCKED")
except PermissionError as e:
    print(f"FORK_BLOCKED: {e}")
except Exception as e:
    print(f"FORK_ERROR: {type(e).__name__}")
"""
    malicious_script = os_client.sandbox_dir / "evil_spawn.py"
    malicious_script.write_text(malicious_code, encoding="utf-8")

    res = await executor.execute_script("sandbox/evil_spawn.py")
    assert res.is_success is True, res.message

    # Ни одно из 4 семейств не должно спакнуть процессы
    assert "SPAWN_WORKED" not in res.message
    assert "POSIX_WORKED" not in res.message
    assert "SPAWNLP_NOT_BLOCKED" not in res.message
    assert "POSIX_SPAWN_NOT_BLOCKED" not in res.message
    assert "EXECVP_NOT_BLOCKED" not in res.message
    assert "FORK_NOT_BLOCKED" not in res.message

    # И все четыре должны ответить PermissionError от гарда
    assert "SPAWNLP_BLOCKED:" in res.message
    assert "POSIX_SPAWN_BLOCKED:" in res.message
    assert "EXECVP_BLOCKED:" in res.message
    assert "FORK_BLOCKED:" in res.message
