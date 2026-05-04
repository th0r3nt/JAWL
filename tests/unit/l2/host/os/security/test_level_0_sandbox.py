import pytest
import os
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.fixture(autouse=True)
def set_sandbox_level(os_client):
    os_client.access_level = HostOSAccessLevel.SANDBOX


def test_sandbox_escape_path_traversal(os_client):
    """
    АТАКА: Классический Path Traversal. Агент передает относительный путь
    с точками, надеясь выйти из песочницы и прочитать код ядра.
    """
    # Агент просит прочитать "sandbox/../src/main.py"
    with pytest.raises(
        PermissionError, match="SANDBOX: Доступ разрешен строго внутри sandbox/"
    ):
        os_client.validate_path("../src/main.py", is_write=False)

    # Жесткий спам точками
    with pytest.raises(PermissionError, match="SANDBOX"):
        os_client.validate_path("../../../../../main.py", is_write=False)


def test_sandbox_escape_absolute_path(os_client):
    """
    АТАКА: Агент игнорирует относительные пути и сразу бьет абсолютным
    в корень операционной системы хоста.
    """
    forbidden_path = "C:\\Windows\\System32\\cmd.exe" if os.name == "nt" else "/etc/shadow"

    with pytest.raises(PermissionError, match="SANDBOX"):
        os_client.validate_path(forbidden_path, is_write=False)

    with pytest.raises(PermissionError, match="SANDBOX"):
        os_client.validate_path(forbidden_path, is_write=True)


def test_sandbox_fake_framework_folder(os_client):
    """
    АТАКА: Агент передает путь к корневой папке фреймворка без префикса sandbox/.
    Так как DWIM логика отключена, это трактуется как выход из песочницы.
    """
    with pytest.raises(PermissionError, match="SANDBOX: Доступ разрешен строго внутри sandbox/"):
        os_client.validate_path(
            f"{os_client.framework_dir.name}/fake_core.py", is_write=True
        )