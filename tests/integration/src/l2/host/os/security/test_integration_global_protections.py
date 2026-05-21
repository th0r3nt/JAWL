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
    ATTACK: Root agent attempts reading protected .env credentials.
    """
    os_client.access_level = HostOSAccessLevel.ROOT
    os_client.config.env_access = False

    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(os_client.framework_dir / ".env", is_write=False)

    with pytest.raises(PermissionError, match="SYSTEM DENIED"):
        os_client.validate_path(
            os_client.framework_dir / "config" / ".env.dev", is_write=False
        )


def test_hacker_sabotage_system_daemons(os_client):
    """
    ATTACK: Sabotaging internal framework API utilities.
    """
    os_client.access_level = HostOSAccessLevel.ROOT

    api_path = os_client.system_dir / "framework_api.py"

    assert os_client.validate_path(api_path, is_write=False) == api_path.resolve()

    with pytest.raises(PermissionError, match="SYSTEM DENIED: Folder 'sandbox/_system/'"):
        os_client.validate_path(api_path, is_write=True)


def test_hacker_system_download_allowance(os_client):
    os_client.access_level = HostOSAccessLevel.SANDBOX

    dl_path = os_client.download_dir / "malware.exe"

    assert os_client.validate_path(dl_path, is_write=True) == dl_path.resolve()


@pytest.mark.asyncio
async def test_attack_zip_slip_vulnerability(os_client, tmp_path):
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    malicious_zip_path = os_client.sandbox_dir / "evil.zip"

    with zipfile.ZipFile(malicious_zip_path, "w") as zf:
        zf.writestr("../../evil_payload.txt", "Hacked!")

    res = await archive_skill.extract_archive(
        str(malicious_zip_path), extract_to="sandbox/extracted"
    )

    assert res.is_success is False
    # FIXED: Expected English error response
    assert "Attempt to escape directory bounds detected" in res.message

    assert not (os_client.sandbox_dir.parent.parent / "evil_payload.txt").exists()


@pytest.mark.asyncio
async def test_attack_tar_symlink_slip(os_client):
    os_client.access_level = HostOSAccessLevel.SANDBOX
    archive_skill = HostOSArchive(os_client)

    malicious_tar_path = os_client.sandbox_dir / "evil.tar"
    with tarfile.open(malicious_tar_path, "w") as tar:
        info = tarfile.TarInfo(name="readme.txt")
        info.size = 5
        tar.addfile(info, io.BytesIO(b"hello"))

        sym_info = tarfile.TarInfo(name="stolen_secrets")
        sym_info.type = tarfile.SYMTYPE
        sym_info.linkname = "/etc/passwd"
        sym_info.size = 0
        tar.addfile(sym_info)

    res = await archive_skill.extract_archive(
        str(malicious_tar_path), extract_to="sandbox/extracted"
    )

    assert res.is_success is False
    # FIXED: Expected English error response
    assert "Attempt to escape directory bounds detected" in res.message

    assert not (os_client.sandbox_dir / "extracted" / "stolen_secrets").exists()


@pytest.mark.asyncio
async def test_attack_tar_symlink_relative_escape(os_client):
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
    os_client.access_level = HostOSAccessLevel.SANDBOX

    mock_gh = MagicMock()
    mock_gh.token = "123"

    git_skill = GithubLocalGit(mock_gh)

    repo_dir = os_client.sandbox_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / ".git").mkdir()

    mock_validate.return_value = repo_dir

    mock_run_git.return_value = (1, "", "error: pathspec '--orphan' did not match")

    res = await git_skill.git_checkout_branch("repo", branch_name="--orphan")

    assert res.is_success is False
    assert "pathspec '--orphan' did not match" in res.message

    mock_run_git.assert_called_once_with(repo_dir, "checkout", "--", "--orphan")


def test_defense_symlink_traversal(os_client):
    os_client.access_level = HostOSAccessLevel.SANDBOX

    symlink_path = os_client.sandbox_dir / "system_root"
    target_root = Path("C:\\") if os.name == "nt" else Path("/")

    try:
        os.symlink(target_root, symlink_path)
    except OSError:
        pytest.skip("Privilege limitations on creating symlinks.")

    file_to_read = "system_root/Windows" if os.name == "nt" else "system_root/etc/passwd"

    with pytest.raises(
        PermissionError, match="SANDBOX: Access is permitted"
    ):
        os_client.validate_path(file_to_read, is_write=False)
