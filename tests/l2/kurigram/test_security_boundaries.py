import re
import sqlite3
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.l0_state.interfaces.state import KurigramState
from src.l2_interfaces.telegram.kurigram import client as client_module
from src.l2_interfaces.telegram.kurigram.bootstrap import setup_kurigram
from src.l2_interfaces.telegram.kurigram.client import (
    KurigramClient,
    ensure_pyrogram_session_compatible,
    validate_pyrogram_session_name,
)
from src.l2_interfaces.telegram.kurigram.skills.account import KurigramAccount
from src.l2_interfaces.telegram.kurigram.skills.admin import KurigramAdmin
from src.l2_interfaces.telegram.kurigram.skills.messages import KurigramMessages


ROOT = Path(__file__).resolve().parents[3]


class _LogSink:
    def __init__(self):
        self.lines = []

    def info(self, message):
        self.lines.append(str(message))

    def warning(self, message):
        self.lines.append(str(message))

    def error(self, message):
        self.lines.append(str(message))

    @property
    def text(self):
        return "\n".join(self.lines)


def _dependency_name(spec):
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", spec)
    return match.group(1).replace("_", "-").lower() if match else ""


def _dependency_specs_from_pyproject(path):
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    def walk(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from walk(item)

    yield from walk(data)


def _dependency_specs_from_requirements(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        spec = line.split("#", 1)[0].strip()
        if spec and not spec.startswith(("-r", "--")):
            yield spec


@pytest.mark.asyncio
async def test_context_block_does_not_expose_env_or_session_secrets(monkeypatch):
    api_hash = "hash_from_dotenv_should_not_leak"
    api_id = "123456_should_not_leak"
    session_path = "/tmp/jawl/agent_kurigram_secret_session"
    session_name = "agent_kurigram_secret_session"
    monkeypatch.setenv("TELETHON_API_ID", api_id)
    monkeypatch.setenv("TELETHON_API_HASH", api_hash)

    state = KurigramState()
    state.is_online = True
    state.account_info = "Профиль: Safe User (@safe_user) | Био: Пусто\n---"
    state.last_chats = "[User] Safe Chat (ID: 42)"
    client = KurigramClient(
        state=state,
        api_id=int(api_id.split("_", 1)[0]),
        api_hash=api_hash,
        session_path=session_path,
        timezone=3,
    )

    context = await client.get_context_block()

    assert "TELETHON_API_HASH" not in context
    assert "TELETHON_API_ID" not in context
    for secret in (api_hash, api_id, session_path, session_name):
        assert secret not in context


@pytest.mark.asyncio
async def test_startup_logs_do_not_expose_api_hash_or_session_path(monkeypatch):
    api_hash = "startup_hash_from_dotenv_should_not_leak"
    session_path = "/tmp/jawl/startup_secret_session"
    log_sink = _LogSink()

    class FakePyrogramClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def start(self):
            return None

        async def get_me(self):
            return SimpleNamespace(
                id=100,
                first_name="Safe",
                last_name="User",
                username="safe_user",
            )

    monkeypatch.setattr(client_module, "Client", FakePyrogramClient)
    monkeypatch.setattr(client_module, "system_logger", log_sink)

    state = KurigramState()
    client = KurigramClient(
        state=state,
        api_id=123456,
        api_hash=api_hash,
        session_path=session_path,
        timezone=3,
    )
    client.update_profile_state = AsyncMock()

    await client.start()

    assert state.is_online is True
    assert api_hash not in log_sink.text
    assert session_path not in log_sink.text
    assert "startup_secret_session" not in log_sink.text


def test_missing_env_log_names_variables_without_exposing_present_secret(monkeypatch):
    api_hash = "present_hash_from_dotenv_should_not_leak"
    log_sink = _LogSink()
    monkeypatch.setattr(
        "src.l2_interfaces.telegram.kurigram.bootstrap.system_logger", log_sink
    )

    components = setup_kurigram(
        system=object(),
        api_id=None,
        api_hash=api_hash,
    )

    assert components == []
    assert "TELETHON_API_HASH" in log_sink.text
    assert ".env" in log_sink.text
    assert api_hash not in log_sink.text


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.account.validate_sandbox_path")
async def test_account_avatar_upload_is_stopped_by_sandbox_validation(
    mock_validate, mock_kurigram_client
):
    mock_validate.side_effect = PermissionError("blocked by sandbox")
    mock_kurigram_client.client().set_profile_photo = AsyncMock()

    result = await KurigramAccount(mock_kurigram_client).change_avatar("../.env")

    assert result.is_success is False
    assert result.message == "blocked by sandbox"
    mock_validate.assert_called_once_with("../.env")
    mock_kurigram_client.client().set_profile_photo.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.account.validate_sandbox_path")
async def test_account_avatar_download_is_stopped_by_sandbox_validation(
    mock_validate, mock_kurigram_client
):
    mock_validate.side_effect = PermissionError("blocked by sandbox")
    mock_kurigram_client.client().get_chat_photos = AsyncMock()
    mock_kurigram_client.client().download_media = AsyncMock()

    result = await KurigramAccount(mock_kurigram_client).download_avatar(
        user_or_chat_id="safe_user",
        dest_filename="../session.sqlite",
    )

    assert result.is_success is False
    assert result.message == "blocked by sandbox"
    mock_validate.assert_called_once_with("../session.sqlite")
    mock_kurigram_client.client().get_chat_photos.assert_not_called()
    mock_kurigram_client.client().download_media.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.messages.validate_sandbox_path")
async def test_message_file_upload_is_stopped_by_sandbox_validation(
    mock_validate, mock_kurigram_client
):
    mock_validate.side_effect = PermissionError("blocked by sandbox")
    mock_kurigram_client.client().send_document = AsyncMock()

    result = await KurigramMessages(mock_kurigram_client).send_file(
        chat_id=123,
        file_path="../.env",
        caption="do not leak",
    )

    assert result.is_success is False
    assert result.message == "blocked by sandbox"
    mock_validate.assert_called_once_with("../.env")
    mock_kurigram_client.client().send_document.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.messages.validate_sandbox_path")
async def test_message_file_download_is_stopped_by_sandbox_validation(
    mock_validate, mock_kurigram_client
):
    mock_validate.side_effect = PermissionError("blocked by sandbox")
    mock_kurigram_client.client().get_messages = AsyncMock()
    mock_kurigram_client.client().download_media = AsyncMock()

    result = await KurigramMessages(mock_kurigram_client).download_file(
        chat_id=123,
        message_id=456,
        dest_filename="../session.sqlite",
    )

    assert result.is_success is False
    assert result.message == "blocked by sandbox"
    mock_validate.assert_called_once_with("../session.sqlite")
    mock_kurigram_client.client().get_messages.assert_not_awaited()
    mock_kurigram_client.client().download_media.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.admin.validate_sandbox_path")
async def test_admin_avatar_upload_is_stopped_by_sandbox_validation(
    mock_validate, mock_kurigram_client
):
    mock_validate.side_effect = PermissionError("blocked by sandbox")
    mock_kurigram_client.client().set_chat_photo = AsyncMock()

    result = await KurigramAdmin(mock_kurigram_client).edit_chat_avatar(
        chat_id=-100500,
        filepath="../.env",
    )

    assert result.is_success is False
    assert result.message == "blocked by sandbox"
    mock_validate.assert_called_once_with("../.env")
    mock_kurigram_client.client().set_chat_photo.assert_not_awaited()


def test_project_dependencies_exclude_legacy_telethon_package():
    dependency_specs = [
        *_dependency_specs_from_requirements(ROOT / "requirements.txt"),
        *_dependency_specs_from_pyproject(ROOT / "pyproject.toml"),
    ]

    legacy_specs = [
        spec for spec in dependency_specs if _dependency_name(spec) == "telethon"
    ]

    assert legacy_specs == []


def test_legacy_session_error_does_not_expose_session_path(tmp_path):
    session_name = "sensitive_agent_session"
    session_file = tmp_path / f"{session_name}.session"
    with sqlite3.connect(session_file) as db:
        db.execute("CREATE TABLE entities (id integer)")

    with pytest.raises(RuntimeError) as exc_info:
        ensure_pyrogram_session_compatible(session_name, tmp_path)

    message = str(exc_info.value)
    assert str(session_file) not in message
    assert str(tmp_path) not in message
    assert session_name not in message
    assert "настроенный session-файл" in message


def test_agent_control_prompts_api_hash_as_password():
    source = (ROOT / "src" / "cli" / "screens" / "agent_control.py").read_text(
        encoding="utf-8"
    )

    assert "api_hash_input = questionary.password(" in source
    assert "Введите TELETHON_API_HASH" in source
    assert 'questionary.text("Введите TELETHON_API_HASH:")' not in source


@pytest.mark.parametrize(
    "bad_name",
    [
        "../outside",
        "../../outside",
        "/tmp/outside",
        "nested/session",
        ".",
        "..",
        "",
    ],
)
def test_config_session_name_cannot_escape_local_session_directory(bad_name):
    with pytest.raises(ValueError):
        validate_pyrogram_session_name(bad_name)


def test_config_session_name_accepts_basename_and_strips_session_suffix():
    assert validate_pyrogram_session_name("agent_kurigram.session") == "agent_kurigram"
