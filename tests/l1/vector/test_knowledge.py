import re
import pytest


def extract_id(log_msg: str) -> str:
    """Вытаскивает UUID из текстового ответа агента."""
    match = re.search(r"ID:\s([a-f0-9\-]+)", log_msg)
    if match:
        return match.group(1)
    raise ValueError(f"Не удалось найти ID в строке: {log_msg}")


@pytest.mark.asyncio
async def test_knowledge_save_and_search(knowledge_manager):
    """Тест: сохранение факта и его успешный семантический поиск."""

    res1 = await knowledge_manager.save_knowledge("Боги смерти едят яблоки")
    res2 = await knowledge_manager.save_knowledge("Машина имеет мощный двигатель")

    assert res1.is_success
    assert res2.is_success

    # Очищаем кэш игнора текущей сессии (иначе Qdrant скроет свежие записи)
    knowledge_manager.clear_session_cache()

    search_result = await knowledge_manager.search_knowledge("Расскажи про яблоки")

    assert search_result.is_success
    assert "яблоки" in search_result.message
    assert "Машина" not in search_result.message


@pytest.mark.asyncio
async def test_knowledge_delete(knowledge_manager):
    """Тест: удаление знания по ID."""

    save_result = await knowledge_manager.save_knowledge("Временный факт")
    assert save_result.is_success

    point_id = extract_id(save_result.message)

    # Очищаем кэш игнора, чтобы get_all_knowledge увидел свежую запись
    knowledge_manager.clear_session_cache()

    all_k = await knowledge_manager.get_all_knowledge()
    assert "Временный факт" in all_k.message

    del_result = await knowledge_manager.delete_knowledge(point_id)
    assert del_result.is_success

    all_k_after = await knowledge_manager.get_all_knowledge()
    assert "пуста" in all_k_after.message


@pytest.mark.asyncio
async def test_knowledge_get_all(knowledge_manager):
    """Тест: чтение массива без семантики (с учетом лимита)."""

    await knowledge_manager.save_knowledge("Факт 1")
    await knowledge_manager.save_knowledge("Факт 2")
    await knowledge_manager.save_knowledge("Факт 3")

    # Сбрасываем сессию, чтобы записи стали видимыми
    knowledge_manager.clear_session_cache()

    result = await knowledge_manager.get_all_knowledge(limit=2)
    assert result.is_success

    count_ids = result.message.count("[ID:")
    assert count_ids == 2


@pytest.mark.asyncio
async def test_knowledge_search_not_found(knowledge_manager):
    """Тест: поиск того, чего нет, не должен ломать систему."""
    # Сохраняем "яблоко", а ищем "шум" (другой вектор)
    await knowledge_manager.save_knowledge("Яблоко")

    search_result = await knowledge_manager.search_knowledge("Неизвестный космос")

    assert search_result.is_success
    assert "не дал результатов" in search_result.message
