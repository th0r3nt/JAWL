import pytest
import os
from unittest.mock import MagicMock
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.fixture(autouse=True)
def set_operator_level(os_client):
    os_client.access_level = HostOSAccessLevel.OPERATOR
    os_client.config.require_deploy_sessions = True
    os_client.deploy_manager = MagicMock()
    os_client.deploy_manager.is_active = False


def test_operator_write_framework_without_session_blocked(os_client):
    """
    АТАКА (ОШИБКА): Агент пытается "на горячую" изменить исходный код,
    не открыв Deploy Session. Это может привести к крашу при SyntaxError.
    """
    core_file = os_client.framework_dir / "src" / "builder.py"

    with pytest.raises(
        PermissionError,
        match="SYSTEM DENIED: Для изменения исходного кода фреймворка необходимо сначала открыть деплой-сессию",
    ):
        os_client.validate_path(core_file, is_write=True)


def test_operator_write_framework_with_session_allowed(os_client):
    """
    ЛЕГАЛЬНО: Агент открыл сессию и модифицирует код.
    Система должна сделать бэкап и пропустить его.
    """
    os_client.deploy_manager.is_active = True
    core_file = os_client.framework_dir / "src" / "builder.py"

    resolved = os_client.validate_path(core_file, is_write=True)

    assert resolved == core_file.resolve()
    # Убеждаемся, что Гейткипер вызвал команду создания Copy-on-Write бэкапа
    os_client.deploy_manager.backup_file.assert_called_once_with(resolved)


def test_operator_sandbox_write_ignores_session(os_client):
    """
    ЛЕГАЛЬНО: Агент без открытой сессии пишет скрипт в песочницу.
    Деплой-сессии требуются только для ядра, в песочнице можно творить хаос свободно.
    """
    sandbox_file = os_client.sandbox_dir / "test_script.py"

    # Пройдет успешно без PermissionError
    resolved = os_client.validate_path(sandbox_file, is_write=True)
    assert resolved == sandbox_file.resolve()

    # Бэкап создаваться не должен
    os_client.deploy_manager.backup_file.assert_not_called()


def test_operator_host_os_breach_blocked(os_client):
    """
    АТАКА: Агент с правами изменения фреймворка пытается выйти за его пределы
    в операционную систему хоста.
    """
    host_file = "C:\\Windows\\System32" if os.name == "nt" else "/etc"

    with pytest.raises(
        PermissionError,
        match="OPERATOR: Доступ \\(чтение и запись\\) разрешен строго только в директории JAWL.",
    ):
        os_client.validate_path(host_file, is_write=True)

    with pytest.raises(PermissionError, match="OPERATOR"):
        os_client.validate_path(host_file, is_write=False)
