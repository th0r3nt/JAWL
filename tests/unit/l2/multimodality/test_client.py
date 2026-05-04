import pytest


@pytest.mark.asyncio
async def test_multimodality_context_block(vision_client):
    """Тест: клиент правильно формирует блок контекста вкл/выкл."""
    vision_client.is_online = True
    ctx = await vision_client.get_context_block()
    assert "MULTIMODALITY [ON]" in ctx

    vision_client.is_online = False
    ctx = await vision_client.get_context_block()
    assert "MULTIMODALITY [OFF]" in ctx
    assert "отключен" in ctx