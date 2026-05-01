import pytest
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.l2_interfaces.host.os.client import HostOSAccessLevel
from src.l2_interfaces.host.os.skills.files.archive import HostOSArchive
from src.l2_interfaces.github.skills.local_git import GithubLocalGit


def test_hacker_steal_env_keys(os_client):
    """
    АТАКА: Агент (даже с правами ROOT) пытается прочитать .env файл,
    чтобы украсть LLM API ключи и отправить их на свой сервер.
    ОЖИДАНИЕ: Блокировка (если env_access = False).
    """
    os_client.access_level = HostOSAccessLevel.ROOT
    os_client.config.env_access = False

    # Попытка 1: Прямое чтение корня
    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(os_client.framework_dir / ".env", is_write=False)

    # Попытка 2: Чтение фейкового .env.dev в подпапке
    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(
            os_client.framework_dir / "config" / ".env.dev", is_write=False
        )


def test_hacker_sabotage_system_daemons(os_client):
    """
    АТАКА: Агент с правами ROOT пытается удалить или изменить системный файл
    'sandbox/_system/framework_api.py', чтобы сломать фоновые процессы.
    ОЖИДАНИЕ: Блокировка. Эта папка - святыня фреймворка.
    """
    os_client.access_level = HostOSAccessLevel.ROOT

    api_path = os_client.system_dir / "framework_api.py"

    # Читать можно
    assert os_client.validate_path(api_path, is_write=False) == api_path.resolve()

    # Изменять/удалять - расстрел
    with pytest.raises(PermissionError, match="SYSTEM DENIED: Папка 'sandbox/_system/'"):
        os_client.validate_path(api_path, is_write=True)


def test_hacker_system_download_allowance(os_client):
    """
    УТОЧНЕНИЕ: При этом агент ОБЯЗАН иметь возможность сохранять файлы
    из интернета в 'sandbox/_system/download/'. Иначе сломаются легальные загрузки.
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX

    dl_path = os_client.download_dir / "malware.exe"

    # Должно пройти успешно
    assert os_client.validate_path(dl_path, is_write=True) == dl_path.resolve()


@pytest.mark.asyncio
async def test_attack_zip_slip_vulnerability(os_client, tmp_path):
    """
    АТАКА (ZIP Slip): Агент пытается распаковать вредоносный архив,
    содержащий выход за пределы директории (Path Traversal).
    ОЖИДАНИЕ: Навык должен проанализировать архив и заблокировать операцию до распаковки.
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    malicious_zip_path = os_client.sandbox_dir / "evil.zip"

    # Создаем вредоносный архив "на лету"
    with zipfile.ZipFile(malicious_zip_path, "w") as zf:
        # Файл пытается выпрыгнуть из песочницы на два уровня вверх
        zf.writestr("../../evil_payload.txt", "Hacked!")

    # Агент пытается распаковать его в песочницу
    res = await archive_skill.extract_archive(str(malicious_zip_path), extract_to="extracted")

    assert res.is_success is False
    assert "Обнаружена попытка выхода за пределы директории" in res.message

    # Убеждаемся, что файл физически не вырвался из песочницы
    assert not (os_client.sandbox_dir.parent.parent / "evil_payload.txt").exists()


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.skills.local_git.GithubLocalGit._run_git_command")
@patch("src.l2_interfaces.github.skills.local_git.validate_sandbox_path")
async def test_attack_git_argument_injection(mock_validate, mock_run_git, os_client):
    """
    АТАКА (Git Injection): Агент передает имя ветки с вредоносным флагом.
    ОЖИДАНИЕ: Git должен воспринять это как имя ветки (из-за разделителя '--').
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX

    mock_gh = MagicMock()
    mock_gh.token = "123"

    git_skill = GithubLocalGit(mock_gh)

    repo_dir = os_client.sandbox_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / ".git").mkdir()

    # Мокаем гейткипер, чтобы он смотрел во временную папку теста, а не в реальную
    mock_validate.return_value = repo_dir

    # Имитируем, что git отвергает такую ветку (но как ветку, а не как исполняемый флаг!)
    mock_run_git.return_value = (1, "", "error: pathspec '--orphan' did not match")

    # Пытаемся передать флаг --orphan вместо имени ветки
    res = await git_skill.git_checkout_branch("repo", branch_name="--orphan")

    assert res.is_success is False
    assert "pathspec '--orphan' did not match" in res.message

    # Самое главное: проверяем, что в команду ушел защитный разделитель '--'
    mock_run_git.assert_called_once_with(repo_dir, "checkout", "--", "--orphan")


def test_defense_symlink_traversal(os_client):
    """
    ЗАЩИТА (Symlink Traversal): Агент (или вредоносный код) создает симлинк
    внутри песочницы, который указывает на системный корень.
    ОЖИДАНИЕ: Path.resolve() вычислит реальный путь, и гейткипер заблокирует доступ.
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX

    symlink_path = os_client.sandbox_dir / "system_root"
    target_root = Path("C:\\") if os.name == "nt" else Path("/")

    try:
        os.symlink(target_root, symlink_path)
    except OSError:
        pytest.skip("ОС не позволяет создавать симлинки без прав администратора.")

    file_to_read = "system_root/Windows" if os.name == "nt" else "system_root/etc/passwd"

    with pytest.raises(PermissionError, match="Доступ разрешен строго внутри sandbox"):
        os_client.validate_path(file_to_read, is_write=False)
