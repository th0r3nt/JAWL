import pytest
import os
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.fixture(autouse=True)
def set_observer_level(os_client):
    os_client.access_level = HostOSAccessLevel.OBSERVER


def test_observer_read_framework_allowed(os_client):
    """
    LEGITIMATE: Agent requests framework read.
    """
    core_file = os_client.framework_dir / "src" / "main.py"

    assert os_client.validate_path("src/main.py", is_write=False) == core_file.resolve()

    with pytest.raises(
        PermissionError, match="OBSERVER: Reading is permitted strictly within JAWL limits."
    ):
        os_client.validate_path("../src/main.py", is_write=False)


def test_observer_write_framework_blocked(os_client):
    """
    ATTACK: Observer agent attempts writing to the core modules.
    """
    core_file = os_client.framework_dir / "src" / "main.py"

    with pytest.raises(
        PermissionError,
        match="OBSERVER: Writing is permitted strictly inside the sandbox/ folder.",
    ):
        os_client.validate_path(core_file, is_write=True)


def test_observer_read_host_os_blocked(os_client):
    """
    ATTACK: Observer agent targets private system files outside of framework limit.
    """
    host_file = (
        "C:\\Users\\Admin\\Desktop\\passwords.txt"
        if os.name == "nt"
        else "/home/user/.ssh/id_rsa"
    )

    with pytest.raises(
        PermissionError, match="OBSERVER: Reading is permitted strictly within JAWL limits."
    ):
        os_client.validate_path(host_file, is_write=False)
