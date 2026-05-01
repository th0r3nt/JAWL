import pytest
import os
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.fixture(autouse=True)
def set_observer_level(os_client):
    os_client.access_level = HostOSAccessLevel.OBSERVER


def test_observer_read_framework_allowed(os_client):
    """
    ЛЕГАЛЬНО: Агент просит прочитать код фреймворка для анализа архитектуры.
    """
    core_file = os_client.framework_dir / "src" / "main.py"

    # Чтение разрешено
    assert os_client.validate_path(core_file, is_write=False) == core_file.resolve()

    # Использование "../" для возврата в корень фреймворка разрешено (DWIM логика)
    assert os_client.validate_path("../src/main.py", is_write=False) == core_file.resolve()


def test_observer_write_framework_blocked(os_client):
    """
    АТАКА: Агент-тестировщик пытается внедрить бэкдор в ядро фреймворка.
    """
    core_file = os_client.framework_dir / "src" / "main.py"

    with pytest.raises(
        PermissionError, match="OBSERVER: Запись разрешена строго в папке sandbox/"
    ):
        os_client.validate_path(core_file, is_write=True)


def test_observer_read_host_os_blocked(os_client):
    """
    АТАКА: Агент пытается прочитать системные логи или файлы хост-ПК юзера.
    Хоть он и OBSERVER, он Observer только для JAWL, а не для всей ОС.
    """
    host_file = (
        "C:\\Users\\Admin\\Desktop\\passwords.txt"
        if os.name == "nt"
        else "/home/user/.ssh/id_rsa"
    )

    with pytest.raises(
        PermissionError, match="OBSERVER: Чтение разрешено только в пределах JAWL."
    ):
        os_client.validate_path(host_file, is_write=False)
