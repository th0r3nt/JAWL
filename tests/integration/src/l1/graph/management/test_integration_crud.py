import pytest

# ====================================================================
# FUZZY MATCH & CONCEPT CREATION
# ====================================================================

@pytest.mark.asyncio
async def test_add_concept_success(graph_manager):
    """Тест: Успешное добавление нового концепта в граф."""
    crud = graph_manager.crud
    
    res = await crud.add_concept(
        name="Python", 
        description="Programming language", 
        category="SOFTWARE"
    )
    
    assert res.is_success is True
    assert "Python" in res.message


@pytest.mark.asyncio
async def test_add_concept_upsert(graph_manager):
    """
    Тест: Добавление концепта с таким же именем (или очень похожим) 
    обновляет существующий (Upsert), а не кидает ошибку.
    """
    crud = graph_manager.crud
    
    await crud.add_concept("Docker haha", "Container engine", "SOFTWARE")
    
    # Агент ошибся на 1 букву или регистр ("docker haha" вместо "Docker haha")
    # Fuzzy match должен найти старый узел и обновить его описание
    res = await crud.add_concept("docker haha", "Updated description", "SOFTWARE")
    
    assert res.is_success is True
    
    # Проверяем, что обновилось именно старое
    neighborhood = await crud.get_concept_neighborhood("Docker haha")
    assert "Updated description" in neighborhood.message
    
    # Убеждаемся, что дубликат не создался
    all_names = crud._get_all_names()
    assert len(all_names) == 1
    assert all_names[0] == "Docker haha"


def test_fuzzy_match_logic(graph_manager):
    """Тест: Внутренняя логика Entity Resolution (Fuzzy Match)."""
    crud = graph_manager.crud
    
    # Вручную создаем узлы для теста алгоритма
    crud.db.conn.execute("CREATE (n:Concept {name: 'Artificial Intelligence', is_active: true})")
    crud.db.conn.execute("CREATE (n:Concept {name: 'Machine Learning', is_active: true})")
    
    # 1. Легкая опечатка (Должно найти)
    match = crud._fuzzy_match("Artificial Inteligenc")
    assert match == "Artificial Intelligence"
    
    # 2. Абсолютно новое слово (Должно вернуть исходник, чтобы потом создать новый узел)
    match_new = crud._fuzzy_match("Blockchain")
    assert match_new == "Blockchain"


# ====================================================================
# EDGES (СВЯЗИ)
# ====================================================================

@pytest.mark.asyncio
async def test_link_concepts_auto_create(graph_manager):
    """
    Тест: При попытке связать два несуществующих узла, 
    система должна сначала их создать, а потом связать.
    """
    crud = graph_manager.crud
    
    res = await crud.link_concepts(
        source_name="API", 
        target_name="Backend", 
        relation="REQUIRES",
        description="Нужно для общения с фронтом"
    )
    
    assert res.is_success is True
    
    # Проверяем, что узлы создались
    names = crud._get_all_names()
    assert "API" in names
    assert "Backend" in names


@pytest.mark.asyncio
async def test_link_concepts_duplicate_prevention(graph_manager):
    """Тест: Повторная попытка создания одинаковой связи не должна создавать дубликат ребра."""
    crud = graph_manager.crud
    
    await crud.link_concepts("A", "B", "RELATES_TO")
    await crud.link_concepts("A", "B", "RELATES_TO") # Дубликат
    
    res = crud.db.conn.execute("MATCH (a:Concept {name: 'A'})-[e:RELATES_TO]->(b:Concept {name: 'B'}) RETURN count(e)")
    edge_count = res.get_next()[0]
    
    assert edge_count == 1  # Ребро должно остаться одним


@pytest.mark.asyncio
async def test_link_concepts_invalid_relation(graph_manager):
    """Тест: Pydantic и внутренняя валидация блокируют выдуманные связи."""
    crud = graph_manager.crud
    
    res = await crud.link_concepts("A", "B", "MAGIC_LINK")
    assert res.is_success is False
    assert "Неизвестный тип связи" in res.message


# ====================================================================
# NEIGHBORHOOD (ВЫВОД КОНТЕКСТА)
# ====================================================================

@pytest.mark.asyncio
async def test_get_concept_neighborhood(graph_manager):
    """Тест: Исследование узла возвращает правильный Markdown со всеми входящими и исходящими связями."""
    crud = graph_manager.crud
    
    await crud.add_concept("Agent", "Autonomous system", "SOFTWARE")
    
    await crud.link_concepts("Agent", "LLM", "REQUIRES", "Для мыслей")
    await crud.link_concepts("Developer", "Agent", "OWNS", "Создатель")
    
    res = await crud.get_concept_neighborhood("Agent")
    assert res.is_success is True
    
    content = res.message
    assert "Концепт: Agent" in content
    assert "Autonomous system" in content
    # Исходящая связь
    assert "-[REQUIRES]-> (LLM) (Для мыслей)" in content
    # Входящая связь
    assert "<-[OWNS]- от (Developer) (Создатель)" in content


@pytest.mark.asyncio
async def test_get_concept_neighborhood_not_found(graph_manager):
    """Тест: Обработка запроса на несуществующий узел."""
    crud = graph_manager.crud
    
    res = await crud.get_concept_neighborhood("Ghost")
    assert res.is_success is True # Это не сбой навыка, а нормальный ответ LLM
    assert "не найден в графе" in res.message


# ====================================================================
# DELETION & ARCHIVATION
# ====================================================================

@pytest.mark.asyncio
async def test_archive_concept(graph_manager):
    """Тест: Архивация (Soft Delete) скрывает узел из поиска."""
    crud = graph_manager.crud
    
    await crud.add_concept("LegacyApp", "Old stuff", "SOFTWARE")
    
    res_archive = await crud.archive_concept("LegacyApp")
    assert res_archive.is_success is True
    
    # При исследовании должно сказать, что он в архиве
    res_explore = await crud.get_concept_neighborhood("LegacyApp")
    assert "был заархивирован" in res_explore.message


@pytest.mark.asyncio
async def test_remove_link(graph_manager):
    """Тест: Выборочное удаление связи между узлами."""
    crud = graph_manager.crud
    
    await crud.link_concepts("Module A", "Module B", "RELATES_TO")
    
    res_remove = await crud.remove_link("Module A", "Module B", "RELATES_TO")
    assert res_remove.is_success is True
    
    # Проверяем, что узлы остались, а связь исчезла
    res_explore = await crud.get_concept_neighborhood("Module A")
    assert "Изолированный узел" in res_explore.message


@pytest.mark.asyncio
async def test_erase_concept(graph_manager):
    """Тест: Жесткое удаление узла каскадно удаляет все его связи."""
    crud = graph_manager.crud
    
    await crud.link_concepts("Center", "Satellite", "PART_OF")
    
    res_erase = await crud.erase_concept("Center")
    assert res_erase.is_success is True
    
    # Center уничтожен
    res_explore = await crud.get_concept_neighborhood("Center")
    assert "не найден в графе" in res_explore.message
    
    # Satellite выжил, но потерял связи
    res_sat = await crud.get_concept_neighborhood("Satellite")
    assert "Изолированный узел" in res_sat.message