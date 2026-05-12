"""
End-to-End тест для навыка Deep Research (OSINT).

Поднимает реальный локальный HTTP-сервер с фейковыми статьями (с мусорным HTML).
Натравливает на них Оркестратор DeepResearch.

Проверяет:
1. Способность параллельно скачивать страницы (физические HTTP-запросы).
2. Очистку от HTML-мусора (<script>, <style>).
3. Динамическую обрезку текста для защиты контекстного окна LLM.
"""

import pytest
import pytest_asyncio
from aiohttp import web
from unittest.mock import AsyncMock, MagicMock

from src.utils.settings import DeepResearchConfig
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l2_interfaces.web.search.skills.trafilatura_read import TrafilaturaReader
from src.l2_interfaces.web.search.skills.research import DeepResearch


async def handle_page1(request: web.Request) -> web.Response:
    html = """
    <html>
        <head><style>body {color: red;}</style></head>
        <body>
            <h1>Page 1: AI News</h1>
            <p>Artificial Intelligence is growing fast.</p>
            <script>console.log("tracker");</script>
        </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def handle_page2(request: web.Request) -> web.Response:
    # Генерируем очень длинный текст для проверки сжатия контекста (Truncation)
    long_text = "This is a very long text. " * 500
    html = f"""
    <html>
        <body>
            <h1>Page 2: Deep Learning</h1>
            <p>{long_text}</p>
        </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


@pytest_asyncio.fixture
async def local_test_server(unused_tcp_port):
    """Фикстура: поднимает aiohttp сервер и возвращает его URL."""
    app = web.Application()
    app.router.add_get("/page1", handle_page1)
    app.router.add_get("/page2", handle_page2)

    runner = web.AppRunner(app)
    await runner.setup()

    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    yield f"http://127.0.0.1:{port}"

    await runner.cleanup()


@pytest.mark.asyncio
async def test_e2e_deep_research_pipeline(local_test_server):
    """E2E Тест: Сбор ссылок -> Загрузка -> Парсинг -> Сжатие -> Отчет."""

    # 1. Настраиваем клиента и лимиты
    config = DeepResearchConfig(
        max_queries=1,
        max_results_per_query=2,
        max_pages_to_read=2,
        total_max_chars=500,  # Жесткий лимит на ОБЕ страницы (по 250 на каждую)
    )

    client_state = MagicMock()
    client_state.add_history = MagicMock()

    web_client = WebSearchClient(
        state=client_state,
        request_timeout=5,
        max_page_chars=10000,
        deep_research_config=config,
    )

    # 2. Мокаем Searcher, чтобы он "нашел" наш локальный сервер
    mock_searcher = MagicMock()
    mock_searcher.search_raw = AsyncMock(
        return_value=[
            {"title": "Result 1", "href": f"{local_test_server}/page1"},
            {"title": "Result 2", "href": f"{local_test_server}/page2"},
        ]
    )

    # 3. Используем РЕАЛЬНЫЙ парсер Trafilatura
    reader = TrafilaturaReader(client=web_client)

    # 4. Собираем Оркестратор
    research = DeepResearch(client=web_client, searcher=mock_searcher, reader=reader)

    # ==========================
    # ВЫПОЛНЕНИЕ
    # ==========================
    res = await research.deep_research(["What is AI?"])

    # ==========================
    # ПРОВЕРКИ
    # ==========================
    assert res.is_success is True

    # Проверяем Page 1 (очистка от HTML)
    assert "Artificial Intelligence is growing fast." in res.message
    assert "body {color: red;}" not in res.message  # CSS вырезан
    assert "console.log" not in res.message  # JS вырезан

    # Проверяем Page 2 (сжатие контекста)
    assert "This is a very long text" in res.message
    assert "Текст обрезан" in res.message

    # Суммарный отчет: Page 1 (~100) + Page 2 (гарантированный минимум 2000) + заголовки Markdown
    assert len(res.message) < 3000

    # Проверяем сохранение в историю браузера агента
    client_state.add_history.assert_called_once_with("Deep Research: What is AI?")
