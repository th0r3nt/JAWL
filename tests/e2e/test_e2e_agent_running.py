import subprocess
from unittest.mock import patch
from pathlib import Path

from src.utils._tools import is_agent_running


def test_e2e_is_agent_running_cleans_zombie_pid(tmp_path: Path):
    """
    E2E Тест: Обнаружение "процессов-призраков".
    Мы создаем реальный процесс Python, записываем его PID.
    Затем убиваем процесс. Функция is_agent_running должна понять,
    что процесс мертв, вернуть False и физически удалить мусорный файл agent.pid.
    """
    pid_file = tmp_path / "agent.pid"
    lock_file = tmp_path / "agent.lock"

    # 1. Запускаем реальный процесс-пустышку, который висит 10 секунд
    proc = subprocess.Popen(["python", "-c", "import time; time.sleep(10)"])

    try:
        # 2. Записываем его PID в файл
        pid_file.write_text(str(proc.pid))
        # Имитируем, что лок-файл остался от краша (но процесс его НЕ залочил)
        lock_file.touch()

        # 3. Убиваем процесс (Имитация жесткого краша/Taskkill)
        proc.kill()
        proc.wait()

        # Убеждаемся, что файлы-зомби остались на диске
        assert pid_file.exists()
        assert lock_file.exists()

        # 4. Вызываем нашу функцию проверки с замоканными путями!
        with patch("src.utils._tools.get_pid_file_path", return_value=pid_file), patch(
            "src.utils._tools.get_lock_file_path", return_value=lock_file
        ):

            result = is_agent_running()

            # Функция должна сказать, что агента нет
            assert result is False

            # Функция должна была прибраться за мертвецом!
            assert not pid_file.exists()
            assert not lock_file.exists()

    finally:
        # На всякий случай добиваем пустышку
        if proc.poll() is None:
            proc.kill()


def test_e2e_is_agent_running_ignores_process_without_lock(tmp_path: Path):
    """
    E2E Тест: Защита от совпадения PID (PID Collision).
    Представим, что агент крашнулся, но операционная система выдала
    тот же самый PID другому случайному Python-процессу (например, pip install).
    Функция должна вернуть False, так как этот процесс не держит File Lock.
    """
    pid_file = tmp_path / "agent.pid"
    lock_file = tmp_path / "agent.lock"

    # 1. Запускаем "чужой" Python процесс
    proc = subprocess.Popen(["python", "-c", "import time; time.sleep(10)"])

    try:
        # 2. Записываем его PID
        pid_file.write_text(str(proc.pid))
        lock_file.touch()

        # 3. Вызываем проверку (мокаем ОБА пути)
        with patch("src.utils._tools.get_pid_file_path", return_value=pid_file), patch(
            "src.utils._tools.get_lock_file_path", return_value=lock_file
        ):

            result = is_agent_running()

            # Несмотря на то, что процесс с таким PID жив и это "python",
            # он не держит Mutex-блокировку на agent.pid, поэтому мы считаем агента мертвым!
            assert result is False
            assert not pid_file.exists()
            assert not lock_file.exists()

    finally:
        if proc.poll() is None:
            proc.kill()
