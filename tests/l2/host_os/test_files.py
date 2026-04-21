import pytest
from src.l2_interfaces.host.os.skills.files import HostOSFiles


@pytest.mark.asyncio
async def test_os_files_write_and_read(os_client):
    """Тест: запись файла в песочницу и его чтение."""
    files = HostOSFiles(os_client)
    filepath = str(os_client.sandbox_dir / "hello.txt")

    # Пишем
    res_write = await files.write_file(filepath, "Hello World", mode="w")
    assert res_write.is_success is True

    # Читаем
    res_read = await files.read_file(filepath)
    assert res_read.is_success is True
    assert "Hello World" in res_read.message


@pytest.mark.asyncio
async def test_os_files_delete_out_of_bounds(os_client):
    """Тест: агент не должен иметь возможности удалять файлы вне песочницы на 1 уровне."""
    files = HostOSFiles(os_client)
    forbidden_path = str(os_client.framework_dir / "main.py")

    res_del = await files.delete_file(forbidden_path)
    assert res_del.is_success is False
    assert "OBSERVER: Запись разрешена строго в папке" in res_del.message


@pytest.mark.asyncio
async def test_os_files_delete_directory(os_client):
    """Тест: успешное рекурсивное удаление папки."""
    files = HostOSFiles(os_client)

    # Создаем папку и файл внутри
    target_dir = os_client.sandbox_dir / "target_folder"
    target_dir.mkdir()
    (target_dir / "inner_file.txt").touch()

    # Удаляем
    res = await files.delete_directory(str(target_dir))

    assert res.is_success is True
    assert not target_dir.exists()


@pytest.mark.asyncio
async def test_os_files_delete_directory_root_protection(os_client):
    """Тест: попытка удалить корень песочницы или фреймворка блокируется."""
    files = HostOSFiles(os_client)

    # Пытаемся снести всю песочницу
    res = await files.delete_directory(str(os_client.sandbox_dir))

    assert res.is_success is False
    assert "Запрещено удалять корневую директорию" in res.message
    assert os_client.sandbox_dir.exists()  # Папка должна выжить


@pytest.mark.asyncio
async def test_os_files_create_directories(os_client):
    """Тест: массовое создание вложенных директорий."""
    files = HostOSFiles(os_client)

    # Передаем два пути. Один простой, второй вложенный
    paths = [
        str(os_client.sandbox_dir / "docs"),
        str(os_client.sandbox_dir / "src" / "api" / "v1"),
    ]

    res = await files.create_directories(paths)

    assert res.is_success is True
    assert (os_client.sandbox_dir / "docs").exists()
    assert (os_client.sandbox_dir / "src" / "api" / "v1").exists()
    assert "Успешно созданы директории: docs, v1" in res.message
