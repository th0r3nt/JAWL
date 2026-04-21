import pytest


@pytest.mark.asyncio
async def test_meta_client_update_setting(meta_client, temp_settings_file):
    """Тест: MetaClient должен физически перезаписывать yaml файл."""

    success = await meta_client.update_setting(
        path_keys=["llm", "model_name"], new_value="new-fast-model"
    )

    assert success is True

    content = temp_settings_file.read_text(encoding="utf-8")
    assert "new-fast-model" in content
    assert "claude-opus-4.7" not in content
