import asyncio
from typing import List, Any

from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.web.search.client import WebSearchClient

from src.l3_agent.skills.registry import skill, SkillResult


class DeepResearch:
    """
    Навыки для глубокого параллельного ресерча в интернете.
    """

    def __init__(self, client: WebSearchClient, searcher: Any, reader: Any):
        self.client = client
        self.searcher = searcher
        self.reader = reader

    @skill()
    async def deep_research(self, queries: List[str]) -> SkillResult:
        """
        Проводит глубокое исследование по списку разных поисковых запросов (рекомендуется от 3 до 10).
        Параллельно ищет информацию, отсекает дубликаты ссылок и читает текстовое содержимое уникальных веб-страниц.
        """

        if not queries:
            return SkillResult.fail("Ошибка: Список запросов пуст.")

        # Берем настройки из клиента
        cfg = self.client.deep_research_config

        if len(queries) > cfg.max_queries:
            # Ограничиваем количество параллельных запросов для стабильности DDGS
            queries = queries[: cfg.max_queries]

        try:
            system_logger.info(f"[Web] Запуск deep_research для {len(queries)} запросов.")

            # Шаг 1: Параллельный поиск по всем запросам
            search_tasks = [
                self.searcher.search_raw(q, max_results=cfg.max_results_per_query)
                for q in queries
            ]
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Шаг 2: Сбор уникальных ссылок и отсечение дублей
            unique_links = {}
            for res in search_results:
                if isinstance(res, Exception) or not res:
                    continue

                for item in res:
                    url = item.get("href")
                    title = item.get("title", "Unknown Title")
                    # Защита от дублей
                    if url and url not in unique_links:
                        unique_links[url] = title

            if not unique_links:
                return SkillResult.fail(
                    "По заданным запросам не удалось найти полезных ссылок."
                )

            # Шаг 3: Ограничиваем количество страниц для чтения
            urls_to_read = list(unique_links.keys())[: cfg.max_pages_to_read]

            # Шаг 4: Параллельное чтение страниц
            read_tasks = [self.reader.read_raw(url) for url in urls_to_read]
            read_results = await asyncio.gather(*read_tasks, return_exceptions=True)

            # Шаг 5: Форматирование результата
            # Динамически режем каждую страницу, чтобы общий объем текста не вылетел за лимиты контекста агента.
            chars_per_page = max(2000, cfg.total_max_chars // len(urls_to_read))

            final_blocks = []
            for i, url in enumerate(urls_to_read):
                title = unique_links[url]
                content = read_results[i]

                # Пропускаем страницы, которые вернули ошибку
                if isinstance(content, Exception) or not content:
                    continue

                content_str = str(content)
                truncated_content = truncate_text(
                    content_str,
                    chars_per_page,
                    "... [Текст обрезан для экономии контекста]",
                )

                block = f"### Title: {title}\nURL: {url}\n\n{truncated_content}\n"
                final_blocks.append(block)

            if not final_blocks:
                return SkillResult.fail(
                    "Ссылки найдены, но не удалось извлечь текст ни с одной из страниц (возможна защита от парсинга)."
                )

            # Добавляем в историю браузера агента один общий лог
            queries_str = ", ".join(queries)
            self.client.state.add_history(f"Deep Research: {queries_str}")

            system_logger.info(
                f"[Web] deep_research успешно завершен (прочитано {len(final_blocks)} страниц)."
            )

            return SkillResult.ok("\n\n---\n\n".join(final_blocks))

        except Exception as e:
            return SkillResult.fail(f"Критическая ошибка во время deep_research: {e}")
