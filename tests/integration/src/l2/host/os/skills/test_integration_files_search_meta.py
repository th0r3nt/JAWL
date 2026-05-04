import pytest
from src.l2_interfaces.host.os.skills.files.search import HostOSSearch
from src.l2_interfaces.host.os.skills.files.metadata import HostOSMetadata
from src.l2_interfaces.host.os.skills.files.archive import HostOSArchive
import zipfile


@pytest.mark.asyncio
async def test_search_list_directory(os_client, tmp_path):
    """Тест: листинг директории строит правильное ASCII дерево."""
    search = HostOSSearch(os_client)
    
    # Подготовка структуры
    target_dir = os_client.sandbox_dir / "my_project"
    target_dir.mkdir()
    (target_dir / "main.py").write_text("print('test')", encoding="utf-8")
    (target_dir / ".hidden").touch()
    
    res = await search.list_directory("sandbox/my_project", max_depth=1)
    
    assert res.is_success is True
    assert "my_project" in res.message
    assert "main.py" in res.message
    assert ".hidden" not in res.message  # Скрытые файлы фильтруются


@pytest.mark.asyncio
async def test_search_files_by_pattern(os_client):
    """Тест: поиск файлов по паттерну."""
    search = HostOSSearch(os_client)
    
    (os_client.sandbox_dir / "test1.py").touch()
    (os_client.sandbox_dir / "test2.log").touch()
    
    res = await search.search_files("*.py", "sandbox")
    
    assert res.is_success is True
    assert "test1.py" in res.message
    assert "test2.log" not in res.message


@pytest.mark.asyncio
async def test_search_content_in_files(os_client):
    """Тест: глобальный поиск строки (grep) по содержимому файлов."""
    search = HostOSSearch(os_client)
    
    f1 = os_client.sandbox_dir / "app.py"
    f1.write_text("def auth():\n    secret = 'PASSWORD_123'\n", encoding="utf-8")
    
    f2 = os_client.sandbox_dir / "config.json"
    f2.write_text('{"token": "PASSWORD_123"}', encoding="utf-8")
    
    res = await search.search_content_in_files("PASSWORD_123", "sandbox")
    
    assert res.is_success is True
    assert "app.py:2" in res.message
    assert "config.json:1" in res.message


@pytest.mark.asyncio
async def test_set_file_metadata(os_client):
    """Тест: привязка метаданных к файлу."""
    meta_skill = HostOSMetadata(os_client)
    
    test_file = os_client.sandbox_dir / "image.png"
    test_file.touch()
    
    res = await meta_skill.set_file_description("sandbox/image.png", "Это скриншот окна браузера.")
    
    assert res.is_success is True
    
    # Проверяем реестр
    meta_data = os_client.get_file_metadata()
    assert "image.png" in meta_data
    assert meta_data["image.png"] == "Это скриншот окна браузера."


@pytest.mark.asyncio
async def test_extract_archive_success(os_client):
    """Тест: успешная (легальная) распаковка архива (позитивный кейс)."""
    archive_skill = HostOSArchive(os_client)
    
    zip_path = os_client.sandbox_dir / "test.zip"
    extract_path = os_client.sandbox_dir / "extracted"
    
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("safe_file.txt", "Safe content")
        
    res = await archive_skill.extract_archive("sandbox/test.zip", "sandbox/extracted")
    
    assert res.is_success is True
    assert (extract_path / "safe_file.txt").exists()
    assert (extract_path / "safe_file.txt").read_text() == "Safe content"