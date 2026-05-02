"""
Интеграционные тесты для механизма деплой-сессий (Deploy Sessions).
Проверяют физическую изоляцию и откат сломанного кода (Rollback).
"""

import pytest
from pathlib import Path

from src.l2_interfaces.host.os.deploy_manager import HostOSDeployManager


@pytest.mark.asyncio
async def test_integration_deploy_rollback_on_syntax_error(tmp_path: Path):
    """
    Интеграционный тест: "Агент пишет сломанный код -> Ядро ловит синтаксическую ошибку -> Rollback".
    Мы используем реальный физический вызов 'sys.executable -m compileall', чтобы
    доказать, что система сама защитит себя от невалидного Python-кода.
    """

    # 1. Подготавливаем фейковую директорию фреймворка
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # Создаем рабочий файл
    test_file = src_dir / "core_module.py"
    test_file.write_text("def my_func():\n    return True\n", encoding="utf-8")

    # Инициализируем менеджера деплоя (выдаем всего 1 попытку для теста)
    manager = HostOSDeployManager(framework_dir=tmp_path, max_retries=1)

    # 2. Агент открывает сессию
    success, msg = manager.start_session()
    assert success is True

    # 3. Агент делает бэкап и вносит СИНТАКСИЧЕСКУЮ ОШИБКУ в код ядра
    manager.backup_file(test_file)
    broken_code = "def my_func() -> str  # Забыл двоеточие и кавычки\n    return 42"
    test_file.write_text(broken_code, encoding="utf-8")

    # 4. Агент пытается закоммитить изменения
    # Вызов коммита физически запустит сабпроцесс `compileall`
    success, commit_msg = await manager.commit_session()

    # 5. ПРОВЕРКА РЕЗУЛЬТАТОВ
    assert success is False
    assert "Синтаксическая ошибка" in commit_msg
    assert "Попытки исчерпаны" in commit_msg

    # Главная проверка: система должна была сама физически вернуть старый, рабочий код
    recovered_code = test_file.read_text(encoding="utf-8")
    assert recovered_code == "def my_func():\n    return True\n"

    # Папка с бэкапами должна быть удалена
    assert not manager.backup_dir.exists()
