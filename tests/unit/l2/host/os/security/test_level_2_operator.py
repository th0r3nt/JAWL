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
    ATTACK: Changing core modules 'on the fly' without active deploy sessions.
    """
    core_file = os_client.framework_dir / "src" / "builder.py"

    with pytest.raises(
        PermissionError,
        match="SYSTEM DENIED: Modifying framework source code requires an active deploy session",
    ):
        os_client.validate_path(core_file, is_write=True)


def test_operator_write_framework_with_session_allowed(os_client):
    """
    LEGITIMATE: Active deploy session allows core writing.
    """
    os_client.deploy_manager.is_active = True
    core_file = os_client.framework_dir / "src" / "builder.py"

    resolved = os_client.validate_path(core_file, is_write=True)

    assert resolved == core_file.resolve()
    os_client.deploy_manager.backup_file.assert_called_once_with(resolved)


def test_operator_sandbox_write_ignores_session(os_client):
    """
    LEGITIMATE: Writing to sandbox bypassing active deploy session constraints.
    """
    sandbox_file = os_client.sandbox_dir / "test_script.py"

    resolved = os_client.validate_path(sandbox_file, is_write=True)
    assert resolved == sandbox_file.resolve()

    os_client.deploy_manager.backup_file.assert_not_called()


def test_operator_host_os_breach_blocked(os_client):
    """
    ATTACK: Operator agent targets files outside of framework bounds.
    """
    host_file = "C:\\Windows\\System32" if os.name == "nt" else "/etc"

    with pytest.raises(
        PermissionError,
        match="OPERATOR: Access \\(read and write\\) is permitted strictly within the JAWL directory.",
    ):
        os_client.validate_path(host_file, is_write=True)

    with pytest.raises(PermissionError, match="OPERATOR: Access"):
        os_client.validate_path(host_file, is_write=False)
