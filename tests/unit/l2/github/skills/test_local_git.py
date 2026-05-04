import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.l2_interfaces.github.skills.local_git import GithubLocalGit


@pytest.fixture
def git_skill(mock_github_client):
    mock_github_client.token = "secret_token_123"
    return GithubLocalGit(mock_github_client)


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.skills.local_git.asyncio.create_subprocess_exec")
@patch("src.l2_interfaces.github.skills.local_git.validate_sandbox_path")
async def test_git_clone_success_and_masking(mock_validate, mock_exec, git_skill, tmp_path):
    """Тест: успешное клонирование и маскировка токена в выводе."""
    mock_path = tmp_path / "repo"
    mock_validate.return_value = mock_path

    # Настраиваем мок подпроцесса
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"Cloned secret_token_123", b""))
    mock_process.returncode = 0
    mock_exec.return_value = mock_process

    res = await git_skill.git_clone_repository("th0r3nt", "JAWL", "repo")

    assert res.is_success is True
    assert "успешно склонирован" in res.message

    # Убеждаемся, что токен был замаскирован в утилите
    masked = git_skill._mask_token("url with secret_token_123 inside")
    assert "secret_token_123" not in masked
    assert "***" in masked


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.skills.local_git.asyncio.create_subprocess_exec")
@patch("src.l2_interfaces.github.skills.local_git.validate_sandbox_path")
async def test_git_commit_and_push(mock_validate, mock_exec, git_skill, tmp_path):
    """Тест: коммит и пуш при наличии изменений."""
    mock_path = tmp_path / "repo"
    # Создаем фиктивную папку .git, чтобы пройти валидацию
    (mock_path / ".git").mkdir(parents=True)
    mock_validate.return_value = mock_path

    # Мокаем 3 вызова (add, status, commit/push)
    mock_process_add = MagicMock(returncode=0)
    mock_process_add.communicate = AsyncMock(return_value=(b"", b""))

    mock_process_status = MagicMock(returncode=0)
    mock_process_status.communicate = AsyncMock(return_value=(b" M file.py", b""))

    mock_process_commit = MagicMock(returncode=0)
    mock_process_commit.communicate = AsyncMock(return_value=(b"Committed", b""))

    mock_process_push = MagicMock(returncode=0)
    mock_process_push.communicate = AsyncMock(return_value=(b"Pushed", b""))

    mock_exec.side_effect = [
        mock_process_add,
        mock_process_status,
        mock_process_commit,
        mock_process_push,
    ]

    res = await git_skill.git_commit_and_push("repo", "Update logic", "main")

    assert res.is_success is True
    assert "успешно зафиксированы" in res.message
    assert mock_exec.call_count == 4


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.skills.local_git.asyncio.create_subprocess_exec")
@patch("src.l2_interfaces.github.skills.local_git.validate_sandbox_path")
async def test_git_commit_clean_tree(mock_validate, mock_exec, git_skill, tmp_path):
    """Тест: прерывание операции, если нет изменений (чистое рабочее дерево)."""
    mock_path = tmp_path / "repo"
    (mock_path / ".git").mkdir(parents=True)
    mock_validate.return_value = mock_path

    mock_process_add = MagicMock(returncode=0)
    mock_process_add.communicate = AsyncMock(return_value=(b"", b""))

    # Status возвращает пустоту (нет изменений)
    mock_process_status = MagicMock(returncode=0)
    mock_process_status.communicate = AsyncMock(return_value=(b"", b""))

    mock_exec.side_effect = [mock_process_add, mock_process_status]

    res = await git_skill.git_commit_and_push("repo", "Update", "main")

    assert res.is_success is True
    assert "Рабочее дерево чистое" in res.message
    assert mock_exec.call_count == 2  # commit и push не вызвались
