import pytest

from src.l0_state.interfaces.state import KurigramState
from src.l2_interfaces.telegram.kurigram.client import KurigramClient


def test_client_splits_legacy_session_path_for_kurigram_workdir():
    state = KurigramState()

    client = KurigramClient(
        state=state,
        api_id=123,
        api_hash="hash",
        session_path="/tmp/jawl/agent_kurigram.session",
        timezone=3,
    )

    assert client.session_name == "agent_kurigram"
    assert client.workdir == "/tmp/jawl"


def test_client_splits_bare_session_name_into_current_workdir():
    state = KurigramState()

    client = KurigramClient(
        state=state,
        api_id=123,
        api_hash="hash",
        session_path="agent_kurigram",
        timezone=3,
    )

    assert client.session_name == "agent_kurigram"
    assert client.workdir == "."


@pytest.mark.asyncio
async def test_context_block_uses_telegram_user_api_header_when_offline():
    client = KurigramClient(
        state=KurigramState(),
        api_id=123,
        api_hash="hash",
        session_path="agent_kurigram",
        timezone=3,
    )

    context = await client.get_context_block()

    assert context.startswith("### TELEGRAM USER API [OFF]")
    assert "Telethon" not in context


@pytest.mark.asyncio
async def test_context_block_uses_telegram_user_api_header_when_online():
    state = KurigramState()
    state.is_online = True
    state.account_info = "Профиль: Test"
    state.last_chats = "Chat | ID: 123"
    client = KurigramClient(
        state=state,
        api_id=123,
        api_hash="hash",
        session_path="agent_kurigram",
        timezone=3,
    )

    context = await client.get_context_block()

    assert context.startswith("### TELEGRAM USER API [ON]")
    assert "Account info: Профиль: Test" in context
    assert "Chat | ID: 123" in context
    assert "Telethon" not in context
