import pytest


@pytest.mark.asyncio
async def test_thoughts_save_and_search(thoughts_manager):
    save_result = await thoughts_manager.save_thought(
        "Я подумал про яблоко", tags=["type:concept"]
    )
    assert save_result.is_success

    search_result = await thoughts_manager.search_thoughts("Что я думал про фрукт?")
    assert search_result.is_success
    assert "Я подумал про яблоко" in search_result.message


@pytest.mark.asyncio
async def test_thoughts_empty_db(thoughts_manager):
    result = await thoughts_manager.get_all_thoughts()
    assert result.is_success
    assert "пуста" in result.message
