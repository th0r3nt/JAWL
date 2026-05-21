import pytest
import os
from pathlib import Path
from src.l2_interfaces.host.os.client import HostOSAccessLevel


def test_gatekeeper_sandbox(os_client):
    os_client.access_level = HostOSAccessLevel.SANDBOX

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"

    assert os_client.validate_path(safe_path) == safe_path.resolve()

    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path(framework_path, is_write=False)


def test_gatekeeper_observer(os_client):
    os_client.access_level = HostOSAccessLevel.OBSERVER

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"
    os_path = Path("/etc/passwd") if os.name != "nt" else Path("C:/Windows/System32/config")

    assert os_client.validate_path(safe_path, is_write=True) == safe_path.resolve()

    with pytest.raises(
        PermissionError,
        match="OBSERVER: Writing is permitted strictly inside the sandbox/ folder.",
    ):
        os_client.validate_path(framework_path, is_write=True)

    assert os_client.validate_path(framework_path, is_write=False) == framework_path.resolve()

    with pytest.raises(
        PermissionError, match="OBSERVER: Reading is permitted strictly within JAWL limits."
    ):
        os_client.validate_path(os_path, is_write=False)


def test_gatekeeper_operator(os_client):
    os_client.access_level = HostOSAccessLevel.OPERATOR

    safe_path = os_client.sandbox_dir / "test.txt"
    framework_path = os_client.framework_dir / "code.py"
    os_path = Path("/etc/passwd") if os.name != "nt" else Path("C:/Windows/System32/config")

    assert os_client.validate_path(safe_path, is_write=True) == safe_path.resolve()

    assert os_client.validate_path(framework_path, is_write=False) == framework_path.resolve()

    with pytest.raises(
        PermissionError,
        match="OPERATOR: Access \\(read and write\\) is permitted strictly within the JAWL directory.",
    ):
        os_client.validate_path(os_path, is_write=False)


def test_gatekeeper_env_protection(os_client):
    os_client.access_level = HostOSAccessLevel.ROOT
    os_client.config.env_access = False

    secret_path = os_client.framework_dir / ".env"
    dev_secret_path = os_client.framework_dir / "config" / ".env.dev"

    with pytest.raises(PermissionError, match="SYSTEM DENIED: Access to configuration files"):
        os_client.validate_path(secret_path, is_write=False)

    with pytest.raises(PermissionError, match="SYSTEM DENIED: Access to configuration files"):
        os_client.validate_path(dev_secret_path, is_write=True)


def test_gatekeeper_framework_api_protection(os_client):
    os_client.access_level = HostOSAccessLevel.ROOT

    api_path = os_client.system_dir / "framework_api.py"

    assert os_client.validate_path(api_path, is_write=False) == api_path.resolve()

    with pytest.raises(
        PermissionError,
        match="SYSTEM DENIED: Folder 'sandbox/_system/' is system-owned and protected.",
    ):
        os_client.validate_path(api_path, is_write=True)

    dl_path = os_client.download_dir / "test.txt"
    assert os_client.validate_path(dl_path, is_write=True) == dl_path.resolve()
