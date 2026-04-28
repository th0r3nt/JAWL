import pytest
import os
from pathlib import Path
from src.l2_interfaces.host.os.client import HostOSAccessLevel


def test_gatekeeper_sandbox(os_client):
    """Тест SANDBOX (0): доступ строго только в sandbox/."""
    os_client.access_level = HostOSAccessLevel.SANDBOX

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"

    # Внутри песочницы - ОК
    assert os_client.validate_path(safe_path) == safe_path.resolve()

    # Чтение фреймворка - Запрещено
    with pytest.raises(PermissionError, match="SANDBOX"):
        os_client.validate_path(framework_path, is_write=False)


def test_gatekeeper_observer(os_client):
    """Тест OBSERVER (1): чтение фреймворка, запись только в sandbox/."""
    os_client.access_level = HostOSAccessLevel.OBSERVER

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"
    os_path = Path("/etc/passwd") if os.name != "nt" else Path("C:/Windows/System32/config")

    # Запись в песочнице - ОК
    assert os_client.validate_path(safe_path, is_write=True) == safe_path.resolve()

    # Запись во фреймворке - Запрещено
    with pytest.raises(PermissionError, match="OBSERVER"):
        os_client.validate_path(framework_path, is_write=True)

    # Чтение фреймворка - ОК
    assert os_client.validate_path(framework_path, is_write=False) == framework_path.resolve()

    # Чтение чужой системы - Запрещено
    with pytest.raises(PermissionError, match="OBSERVER"):
        os_client.validate_path(os_path, is_write=False)


def test_gatekeeper_operator(os_client):
    """Тест OPERATOR (2): чтение и запись (с сессиями) строго внутри фреймворка."""
    os_client.access_level = HostOSAccessLevel.OPERATOR

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"
    os_path = Path("/etc/passwd") if os.name != "nt" else Path("C:/Windows/System32/config")

    # Чтение/запись в песочнице - ОК
    assert os_client.validate_path(safe_path, is_write=True) == safe_path.resolve()

    # Чтение фреймворка - ОК
    assert os_client.validate_path(framework_path, is_write=False) == framework_path.resolve()

    # Чтение чужой системы - Запрещено
    with pytest.raises(PermissionError, match="OPERATOR"):
        os_client.validate_path(os_path, is_write=False)


def test_gatekeeper_env_protection(os_client):
    """Тест: запрет доступа к .env файлам работает даже в режиме ROOT."""
    os_client.access_level = HostOSAccessLevel.ROOT
    os_client.config.env_access = False

    secret_path = os_client.framework_dir / ".env"
    dev_secret_path = os_client.framework_dir / "config" / ".env.dev"

    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(secret_path, is_write=False)

    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(dev_secret_path, is_write=True)

def test_gatekeeper_framework_api_protection(os_client):
    """Тест: защита системного файла framework_api.py от изменения агентом."""
    os_client.access_level = HostOSAccessLevel.ROOT  # Даже рут не может его трогать
    
    api_path = os_client.sandbox_dir / "framework_api.py"
    
    # Чтение разрешено
    assert os_client.validate_path(api_path, is_write=False) == api_path.resolve()
    
    # Любая запись/удаление/перемещение заблокированы
    with pytest.raises(PermissionError, match="SYSTEM DENIED: Файл 'framework_api.py'"):
        os_client.validate_path(api_path, is_write=True)