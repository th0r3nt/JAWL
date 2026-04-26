import re
import pytest


def extract_id(log_msg: str) -> str:
    match = re.search(r"ID:\s([a-f0-9\-]+)", log_msg)
    if match:
        return match.group(1)
    raise ValueError(f"Не удалось найти ID в строке: {log_msg}")


@pytest.mark.asyncio
async def test_knowledge_save_and_search(knowledge_manager):
    res1 = await knowledge_manager.save_knowledge(
        "Боги смерти едят яблоки", tags=["domain:lore"]
    )
    res2 = await knowledge_manager.save_knowledge(
        "Машина имеет мощный двигатель", tags=["domain:tech"]
    )

    assert res1.is_success
    assert res2.is_success

    search_result = await knowledge_manager.search_knowledge("Расскажи про яблоки")
    assert search_result.is_success
    assert "яблоки" in search_result.message


@pytest.mark.asyncio
async def test_knowledge_delete(knowledge_manager):
    save_result = await knowledge_manager.save_knowledge("Временный факт", tags=["type:fact"])
    point_id = extract_id(save_result.message)

    del_result = await knowledge_manager.delete_knowledge(point_id)
    assert del_result.is_success


@pytest.mark.asyncio
async def test_knowledge_get_all(knowledge_manager):
    await knowledge_manager.save_knowledge("Факт 1", tags=["type:fact"])
    await knowledge_manager.save_knowledge("Факт 2", tags=["type:fact"])
    await knowledge_manager.save_knowledge("Факт 3", tags=["type:fact"])

    result = await knowledge_manager.get_all_knowledge(limit=2)
    assert result.message.count("[ID:") == 2


@pytest.mark.asyncio
async def test_knowledge_search_not_found(knowledge_manager):
    await knowledge_manager.save_knowledge("Яблоко", tags=["type:fact"])
    search_result = await knowledge_manager.search_knowledge("Неизвестный космос")
    assert "не дал результатов" in search_result.message
