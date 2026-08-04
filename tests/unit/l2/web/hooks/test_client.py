import pytest


@pytest.mark.asyncio
async def test_hooks_get_context_block(hooks_client):
    """Тест: Формирование блока контекста для системного промпта."""
    hooks_client.state.is_online = True
    hooks_client.state.add_hook("id_1", "GitHub", "12:00", {"event": "push"}, "preview text")

    block = await hooks_client.get_context_block()

    assert "WEB HOOKS [ON]" in block
    assert f"127.0.0.1:{hooks_client.config.port}" in block
    assert "preview text" in block

    hooks_client.state.is_online = False
    block_off = await hooks_client.get_context_block()

    assert "WEB HOOKS [OFF]" in block_off
