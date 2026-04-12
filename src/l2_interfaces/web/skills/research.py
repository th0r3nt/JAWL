import asyncio

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.client import WebClient
from src.l2_interfaces.web.skills.search import WebSearch
from src.l2_interfaces.web.skills.webpages import WebPages


class WebResearch:
    """Оркестратор для глубокого асинхронного ресерча в интернете."""

    def __init__(self, client: WebClient, search_skill: WebSearch, pages_skill: WebPages):
        self.client = client
        self.search = search_skill
        self.pages = pages_skill

    @skill()
    async def deep_research(
        self, queries: list[str], max_links_per_query: int = 4
    ) -> SkillResult:
        """
        Выполняет поиск по массиву запросов (рекомендуется формулировать по-разному) и читает содержимое лучших страниц.
        Рекомендуется для глубокого сбора информации.
        """

        if not queries:
            return SkillResult.fail("Список запросов пуст.")

        try:
            all_urls: dict[str, str] = {}  # URL -> Title (сохраняет уникальность)

            # 1. Параллельный поиск по всем запросам
            search_tasks = [self.search.search_raw(q, max_links_per_query) for q in queries]
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            for res in search_results:
                if isinstance(res, list):
                    for item in res:
                        if item["href"] not in all_urls:
                            all_urls[item["href"]] = item["title"]

            if not all_urls:
                return SkillResult.fail("Не найдено ни одной ссылки по запросам.")

            system_logger.info(
                f"[Web] Deep research: найдено уникальных ссылок - {len(all_urls)}. Читение."
            )

            # Параллельное чтение собранных страниц
            read_tasks = [self.pages.read_raw(url) for url in all_urls.keys()]
            pages_content = await asyncio.gather(*read_tasks, return_exceptions=True)

            # Сборка итогового отчета
            report = []
            char_limit_per_page = 20000

            for (url, title), content in zip(all_urls.items(), pages_content):
                if isinstance(content, Exception) or not content:
                    report.append(f"### {title}\nURL: {url}\n[Ошибка чтения / Блокировка]")
                else:
                    truncated = content[:char_limit_per_page]
                    if len(content) > char_limit_per_page:
                        truncated += "\n... [Текст обрезан]"
                    report.append(f"### {title}\nURL: {url}\n{truncated}")

            system_logger.info(
                f"[Web] Deep research завершен. Обработано {len(queries)} запросов."
            )
            self.client.state.add_history(f"Deep Research по запросам: {', '.join(queries)}")
            return SkillResult.ok("\n\n---\n\n".join(report))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при выполнении deep research: {e}")
