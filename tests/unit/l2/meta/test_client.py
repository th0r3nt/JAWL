import pytest


@pytest.mark.asyncio
async def test_meta_client_update_yaml_success(meta_client, tmp_settings):
    """Тест: MetaClient корректно обновляет вложенные поля в YAML-файле."""
    res = await meta_client.update_yaml(tmp_settings, ["llm", "model"], "new-model-2000")

    assert res is True
    content = tmp_settings.read_text(encoding="utf-8")
    assert "new-model-2000" in content


@pytest.mark.asyncio
async def test_meta_client_get_context_block(meta_client):
    """Тест: Блок контекста содержит правильную инфу о доступе и моделях."""
    block = await meta_client.get_context_block()

    assert "META [ON]" in block
    assert "Access Level: 2" in block
    assert "claude-opus-4.7, gpt-4o" in block
