import pytest
import os
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.fixture(autouse=True)
def set_sandbox_level(os_client):
    os_client.access_level = HostOSAccessLevel.SANDBOX


def test_sandbox_escape_path_traversal(os_client):
    """
    ATTACK: Classic Path Traversal. Agent sends relative paths with dots
    expecting to escape sandbox bounds and read kernel files.
    """
    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path("../src/main.py", is_write=False)

    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path("../../../../../main.py", is_write=False)


def test_sandbox_escape_absolute_path(os_client):
    """
    ATTACK: Direct absolute file path bypass targeting system root files.
    """
    forbidden_path = "C:\\Windows\\System32\\cmd.exe" if os.name == "nt" else "/etc/shadow"

    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path(forbidden_path, is_write=False)

    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path(forbidden_path, is_write=True)


def test_sandbox_fake_framework_folder(os_client):
    """
    ATTACK: Agent bypasses prepending sandbox/ by manually including the JAWL root folder name.
    """
    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path(f"{os_client.framework_dir.name}/fake_core.py", is_write=True)
