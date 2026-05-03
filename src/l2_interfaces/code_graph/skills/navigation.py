"""
Навыки для навигации в Кодовых графах.

Кодовые графы хранят зависимости, описания и помогают разбираться в сложных кодовых базах,
благодаря векторному поиску по связям в детерминированном графе.
"""

from typing import Optional

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l1_databases.graph.management.crud_ast import GraphASTCRUD
from src.l1_databases.vector.management.code_ast import VectorCodeAST


class CodeGraphNavigation:
    """
    Навыки для мгновенного поиска и анализа связей в коде (Agentic Introspection).
    """

    def __init__(
        self, client: CodeGraphClient, graph_crud: GraphASTCRUD, vector_crud: VectorCodeAST
    ):
        self.client = client
        self.graph = graph_crud
        self.vector = vector_crud

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def search_code_semantic(
        self, project_id: str, query: str, limit: Optional[int] = None
    ) -> SkillResult:
        """
        Семантический поиск по докстрингам классов и функций проекта.
        Полезно, если нет информации о названии функции, но есть информация о том, что она должна делать.
        Например: 'где сохраняются логи тиков'

        Args:
            project_id: ID проиндексированного графа.
            query: Смысловой текстовый запрос.
        """

        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(
                f"Проект '{project_id}' не найден. Сначала проиндексируйте его."
            )

        try:
            search_limit = limit if limit is not None else self.client.config.max_search_results
            results = await self.vector.search(query, project_id, search_limit)

            if not results:
                return SkillResult.ok(
                    f"По семантическому запросу '{query}' совпадений не найдено."
                )

            lines = [f"Результаты семантического поиска ('{query}'):"]
            for r in results:
                # Парсим ID узла: 'project_id::src/file.py::ClassName' -> берем только 'src/file.py::ClassName'
                clean_id = r["node_id"].replace(f"{project_id}::", "")
                desc = r["text"].replace("\n", " ")
                # Обрезаем докстринг для вывода
                desc = desc[:150] + "..." if len(desc) > 150 else desc

                lines.append(
                    f"- [{r['type']}] `{clean_id}` (Сходство: {r['score']:.2f})\n  Докстринг: {desc}"
                )

            system_logger.info(f"[Code Graph] Семантический поиск по '{query}' завершен.")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка семантического поиска: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def trace_dependencies(self, project_id: str, target_name: str) -> SkillResult:
        """
        Поиск "радиуса поражения". Показывает, в каких файлах импортируется
        указанный файл, или какие функции находятся внутри класса.
        Например: полезно перед рефакторингом, чтобы понять, какие тесты нужно обновить.

        Args:
            project_id: ID проиндексированного графа.
            target_name: Имя файла (например 'src/main.py') или полный путь к классу ('src/main.py::MyClass').
        """
        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(f"Проект '{project_id}' не найден.")

        node_id = f"{project_id}::{target_name}"

        try:
            # Кто зависит от нас (входящие связи: кто нас импортирует)
            usages = await self.graph.get_usages(node_id)

            # От кого зависим мы (исходящие связи: что мы импортируем / что лежит внутри)
            deps = await self.graph.get_dependencies(node_id)

            if not usages and not deps:
                return SkillResult.ok(
                    f"Узел '{target_name}' не найден в графе или не имеет связей."
                )

            lines = [f"Архитектурные связи для `{target_name}`:\n\n"]

            if usages:
                lines.append("Входящие связи:")
                for u in usages:
                    clean_id = u["id"].replace(f"{project_id}::", "")
                    lines.append(f"  - [{u['relation']}] <- {clean_id} ({u['type']})")

            if deps:
                lines.append("\n\nИсходящие связи:")
                for d in deps:
                    clean_id = d["id"].replace(f"{project_id}::", "")
                    lines.append(f"  - [{d['relation']}] -> {clean_id} ({d['type']})")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка поиска зависимостей: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def get_file_structure(self, project_id: str, filepath: str) -> SkillResult:
        """
        Мгновенно возвращает "оглавление" файла (какие классы и методы в нем есть) без полного чтения кода.

        Args:
            project_id: ID проиндексированного графа.
            filepath: Относительный путь к файлу в фреймворке (например 'src/main.py').
        """

        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(f"Проект '{project_id}' не найден.")

        file_node_id = f"{project_id}::{filepath}"

        try:
            # Ищем все, что содержится в файле (связи CONTAINS)
            contents = await self.graph.get_dependencies(file_node_id)

            if not contents:
                return SkillResult.ok(
                    f"Файл '{filepath}' пуст, не содержит классов/функций, либо не проиндексирован."
                )

            limit = self.client.config.max_structure_items
            lines = [f"Структура файла `{filepath}` (Лимит отображения: {limit}):"]
            count = 0

            for item in contents:
                if count >= limit:
                    lines.append("- ... [Остальные элементы скрыты для экономии контекста]")
                    break

                if item['relation'] == "CONTAINS":
                    clean_name = item['id'].replace(f"{project_id}::{filepath}::", "")
                    count += 1
                    lines.append(f"- [{item['type']}] {clean_name}")

                    # Если это класс, ищем его методы (связь DEFINES)
                    if item["type"] == "CLASS":
                        methods = await self.graph.get_dependencies(item["id"])
                        for m in methods:
                            if m["relation"] == "DEFINES":
                                m_name = m["id"].split(".")[-1]
                                lines.append(f"    - [METHOD] {m_name}")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка получения структуры файла: {e}")
