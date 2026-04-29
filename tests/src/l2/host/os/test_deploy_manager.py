import pytest
from pathlib import Path
from src.l2_interfaces.host.os.deploy_manager import HostOSDeployManager


@pytest.fixture
def deploy_manager(tmp_path: Path):
    """Инициализирует менеджер деплоя во временной директории фреймворка."""
    manager = HostOSDeployManager(framework_dir=tmp_path, max_retries=3)
    return manager


def test_deploy_start_session(deploy_manager):
    """Тест: Успешное открытие деплой-сессии."""
    assert deploy_manager.is_active is False

    success, msg = deploy_manager.start_session()

    assert success is True
    assert deploy_manager.is_active is True
    assert deploy_manager.active_flag.exists()
    assert deploy_manager.manifest_file.exists()
    assert "У вас есть 3 попытки" in msg

    # Попытка открыть вторую сессию
    success_dup, msg_dup = deploy_manager.start_session()
    assert success_dup is False
    assert "уже активна" in msg_dup


def test_deploy_backup_file_copy_on_write(deploy_manager, tmp_path):
    """Тест: Механизм Copy-on-Write корректно бэкапит файл перед изменением."""
    deploy_manager.start_session()

    # Создаем файл "исходного кода"
    src_file = tmp_path / "src" / "test_module.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("print('v1')", encoding="utf-8")

    # Бэкапим
    deploy_manager.backup_file(src_file)

    # Проверяем, что бэкап создался в правильном месте
    backup_path = deploy_manager.backup_dir / "src" / "test_module.py"
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "print('v1')"


def test_deploy_backup_new_file_manifest(deploy_manager, tmp_path):
    """Тест: Если файла не существовало (агент создает новый), он заносится в манифест."""
    deploy_manager.start_session()

    new_file = tmp_path / "src" / "new_feature.py"
    # Файла физически нет, агент только готовится в него записать

    deploy_manager.backup_file(new_file)

    # Файл бэкапа не должен быть создан (нечего копировать)
    backup_path = deploy_manager.backup_dir / "src" / "new_feature.py"
    assert not backup_path.exists()

    # Но он должен попасть в манифест
    manifest_content = deploy_manager.manifest_file.read_text(encoding="utf-8")
    # Используем as_posix для кроссплатформенности слешей при проверке
    assert "src/new_feature.py" in manifest_content.replace("\\", "/")


def test_deploy_rollback_session(deploy_manager, tmp_path):
    """Тест: Rollback возвращает старые файлы и удаляет новые."""
    deploy_manager.start_session()

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # 1. Оригинальный файл (был изменен)
    old_file = src_dir / "old.py"
    old_file.write_text("print('v1')", encoding="utf-8")
    deploy_manager.backup_file(old_file)

    # Агент ломает файл
    old_file.write_text("broken_code()", encoding="utf-8")

    # 2. Новый файл (был создан)
    new_file = src_dir / "new.py"
    deploy_manager.backup_file(new_file)  # Попадет в манифест
    new_file.write_text("print('v2')", encoding="utf-8")

    # Инициируем откат
    success, msg = deploy_manager.rollback_session()

    assert success is True

    # Проверяем восстановление
    assert old_file.read_text(encoding="utf-8") == "print('v1')"  # Вернулся старый код
    assert not new_file.exists()  # Новый файл удалился

    # Проверяем очистку
    assert deploy_manager.is_active is False
    assert not deploy_manager.backup_dir.exists()
