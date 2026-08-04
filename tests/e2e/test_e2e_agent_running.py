"""
E2E тесты жизненного цикла агента и проверки очистки 'зомби'-файлов блокировки (PID/Lock).
"""

import subprocess
from unittest.mock import patch
from pathlib import Path

from src.utils._tools import is_agent_running


def test_e2e_is_agent_running_cleans_zombie_pid(tmp_path: Path):
    """
    E2E тест для проверки корректного обнаружения и очистки 'процессов-призраков'.

    Сценарий:
    1. Инициализируется реальный дочерний процесс Python.
    2. Его PID сохраняется в файл, имитируя состояние работы агента.
    3. Процесс принудительно завершается (имитация сбоя).
    4. Вызывается 'is_agent_running' для валидации статуса:
       - Должен вернуть False (процесс неактивен).
       - Должен инициировать удаление 'зомби'-файлов (agent.pid, agent.lock).
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
    E2E тест для проверки устойчивости к совпадению PID (PID Collision).

    Сценарий:
    1. Процесс крашнулся, PID был переиспользован другим процессом ОС.
    2. Функция 'is_agent_running' должна вернуть False, так как новый процесс
       не удерживает обязательную Mutex-блокировку на agent.lock.
    3. Валидируется корректная очистка старых файлов при отсутствии блокировки.
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
