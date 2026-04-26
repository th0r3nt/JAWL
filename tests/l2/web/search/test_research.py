import pytest
from unittest.mock import AsyncMock
from src.l2_interfaces.web.search.skills.research import DeepResearch
from src.utils.settings import DeepResearchConfig


@pytest.mark.asyncio
async def test_deep_research_success(web_client, search_skill, pages_skill):
    """Тест: DeepResearch правильно собирает ссылки и читает страницы параллельно."""

    # Настраиваем лимиты
    web_client.deep_research_config = DeepResearchConfig(
        max_queries=2, max_results_per_query=2, max_pages_to_read=2, total_max_chars=1000
    )

    # Мокаем сырой поиск
    search_skill.search_raw = AsyncMock(
        return_value=[
            {"title": "Page 1", "href": "https://p1.com"},
            {"title": "Page 2", "href": "https://p2.com"},
        ]
    )

    # Мокаем сырое чтение (возвращаем разные тексты для разных URL)
    async def mock_read_raw(url):
        if "p1.com" in url:
            return "Text 1"
        if "p2.com" in url:
            return "Text 2"
        return None

    pages_skill.read_raw = AsyncMock(side_effect=mock_read_raw)

    research = DeepResearch(web_client, search_skill, pages_skill)
    res = await research.deep_research(["Query A"])

    assert res.is_success is True
    assert "Text 1" in res.message
    assert "Text 2" in res.message

    # Проверяем, что запись упала в историю браузера (L0 State)
    assert len(web_client.state.history) == 1
    assert "Deep Research: Query A" in web_client.state.history[0]
