import pytest
import os
import io
import tarfile
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
    res = await archive_skill.extract_archive(
        str(malicious_zip_path), extract_to="sandbox/extracted"
    )

    assert res.is_success is False
    assert "Обнаружена попытка выхода за пределы директории" in res.message

    # Убеждаемся, что файл физически не вырвался из песочницы
    assert not (os_client.sandbox_dir.parent.parent / "evil_payload.txt").exists()


@pytest.mark.asyncio
async def test_attack_tar_symlink_slip(os_client):
    """
    АТАКА (Tar Symlink Slip): злой tar-архив с symlink'ом, имя которого
    выглядит безопасно внутри sandbox, но linkname указывает на /etc/passwd.
    shutil.unpack_archive на Python <3.12 последует за ним, и агент
    получает чтение секретов через sandbox/link.
    ОЖИДАНИЕ: _is_safe_archive отклоняет архив до распаковки.
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    malicious_tar_path = os_client.sandbox_dir / "evil.tar"
    with tarfile.open(malicious_tar_path, "w") as tar:
        # Безобидный файл для маскировки
        info = tarfile.TarInfo(name="readme.txt")
        info.size = 5
        tar.addfile(info, io.BytesIO(b"hello"))

        # Симлинк на /etc/passwd - имя в sandbox, таргет абсолютный
        sym_info = tarfile.TarInfo(name="stolen_secrets")
        sym_info.type = tarfile.SYMTYPE
        sym_info.linkname = "/etc/passwd"
        sym_info.size = 0
        tar.addfile(sym_info)

    res = await archive_skill.extract_archive(
        str(malicious_tar_path), extract_to="sandbox/extracted"
    )

    assert res.is_success is False
    assert "Обнаружена попытка выхода за пределы директории" in res.message

    # И самое главное — симлинк не должен быть создан
    assert not (os_client.sandbox_dir / "extracted" / "stolen_secrets").exists()


@pytest.mark.asyncio
async def test_attack_tar_symlink_relative_escape(os_client):
    """
    АТАКА (Tar Symlink Slip via relative path): symlink с относительным
    выходом за пределы sandbox (../../../etc/passwd). Тонкий вариант
    предыдущего, обходит проверку is_absolute().
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    malicious_tar_path = os_client.sandbox_dir / "evil_rel.tar"
    with tarfile.open(malicious_tar_path, "w") as tar:
        sym_info = tarfile.TarInfo(name="leak")
        sym_info.type = tarfile.SYMTYPE
        sym_info.linkname = "../../../../../../etc/passwd"
        sym_info.size = 0
        tar.addfile(sym_info)

    res = await archive_skill.extract_archive(
        str(malicious_tar_path), extract_to="sandbox/extracted"
    )

    assert res.is_success is False
    assert not (os_client.sandbox_dir / "extracted" / "leak").exists()


@pytest.mark.asyncio
async def test_attack_tar_hardlink_slip(os_client):
    """
    АТАКА (Tar Hardlink Slip): хардлинк на абсолютный путь. Аналогично
    symlink'у, shutil.unpack_archive на Python <3.12 создаст хардлинк на
    внешний файл.
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    malicious_tar_path = os_client.sandbox_dir / "evil_hl.tar"
    with tarfile.open(malicious_tar_path, "w") as tar:
        hl_info = tarfile.TarInfo(name="shadow_access")
        hl_info.type = tarfile.LNKTYPE
        hl_info.linkname = "/etc/shadow"
        hl_info.size = 0
        tar.addfile(hl_info)

    res = await archive_skill.extract_archive(
        str(malicious_tar_path), extract_to="sandbox/extracted"
    )

    assert res.is_success is False


@pytest.mark.asyncio
async def test_safe_tar_with_relative_symlink_allowed(os_client):
    """
    РЕГРЕСС-ГУАРД: безопасный архив с symlink'ом на соседний файл
    внутри sandbox ДОЛЖЕН распаковываться. Фикс не должен ломать
    легитимные сценарии.
    """
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    safe_tar_path = os_client.sandbox_dir / "safe.tar"
    with tarfile.open(safe_tar_path, "w") as tar:
        info = tarfile.TarInfo(name="real.txt")
        info.size = 5
        tar.addfile(info, io.BytesIO(b"hello"))

        sym_info = tarfile.TarInfo(name="link_to_real")
        sym_info.type = tarfile.SYMTYPE
        sym_info.linkname = "real.txt"
        sym_info.size = 0
        tar.addfile(sym_info)

    res = await archive_skill.extract_archive(
        str(safe_tar_path), extract_to="sandbox/safe_out"
    )

    assert res.is_success is True, res.message


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
