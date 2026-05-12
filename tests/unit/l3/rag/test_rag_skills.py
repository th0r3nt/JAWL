"""
Unit-тесты для навыков ручного управления памятью (RAG).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l3_agent.context.rag.skills import MemoryRecallSkill


@pytest.mark.asyncio
async def test_recall_information_success():
    """Тест: Оркестратор корректно получает запросы и отдает Markdown-результат."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(return_value="RELEVANT INFO:\n- Факт 1")

    skill = MemoryRecallSkill(mock_orchestrator)
    res = await skill.recall_information(["Настройка nginx", "SSL сертификаты"])

    assert res.is_success is True
    assert "Результаты поиска в памяти" in res.message
    assert "Факт 1" in res.message
    mock_orchestrator.run.assert_called_once_with(["Настройка nginx", "SSL сертификаты"])


@pytest.mark.asyncio
async def test_recall_information_empty_queries():
    """Тест: Защита от пустых или мусорных запросов."""
    skill = MemoryRecallSkill(MagicMock())

    # Пустой массив
    res1 = await skill.recall_information([])
    assert res1.is_success is False
    assert "не может быть пустым" in res1.message

    # Массив с пробелами и пустыми строками
    res2 = await skill.recall_information(["   ", ""])
    assert res2.is_success is False
    assert "оказались пустыми" in res2.message


@pytest.mark.asyncio
async def test_recall_information_no_results():
    """Тест: Обработка ситуации, когда поиск в базах ничего не дал."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(return_value="")  # Оркестратор ничего не нашел

    skill = MemoryRecallSkill(mock_orchestrator)
    res = await skill.recall_information(["Инопланетяне"])

    # Скилл считается "успешным", просто факт того, что инфы нет - это тоже инфа
    assert res.is_success is True
    assert "не найдено релевантной информации" in res.message
