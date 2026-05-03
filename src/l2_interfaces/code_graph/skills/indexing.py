"""
Навыки для создания и индексации Кодовых графов.

Кодовые графы хранят зависимости, описания и помогают разбираться в сложных кодовых базах,
благодаря векторному поиску по связям в детерминированном графе.
"""

import ast
import asyncio
from pathlib import Path
from typing import Dict

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l1_databases.graph.management.crud_ast import GraphASTCRUD
from src.l1_databases.vector.management.code_ast import VectorCodeAST


class CodeGraphIndexing:
    """Навык для создания AST-графа кодовой базы."""

    def __init__(
        self, client: CodeGraphClient, graph_crud: GraphASTCRUD, vector_crud: VectorCodeAST
    ):
        self.client = client
        self.graph = graph_crud
        self.vector = vector_crud

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def index_codebase(self, target_dir: str, project_id: str) -> SkillResult:
        """
        Сканирует директорию с кодом и строит граф архитектуры.

        Args:
            target_dir: Путь к папке с кодом (внутри песочницы или фреймворка, в зависимости от прав).
            project_id: Уникальное имя (ID) для этого графа без пробелов.
        """

        try:
            safe_path = self.client.host_os.validate_path(target_dir, is_write=False)
            if not safe_path.is_dir():
                return SkillResult.fail(
                    f"Ошибка: Путь не является директорией ({target_dir})."
                )

            project_id = project_id.strip().replace(" ", "_").lower()

            system_logger.info(
                f"[Code Graph] Запуск индексации проекта '{project_id}' в {safe_path.name}."
            )

            # Асинхронно парсим все файлы чтобы не блочить Event Loop
            stats = await asyncio.to_thread(self._parse_and_build_sync, safe_path, project_id)

            # Сохраняем в стейт
            rel_path = safe_path.relative_to(self.client.host_os.framework_dir).as_posix()
            self.client.state.active_indexes[project_id] = rel_path
            self.client.state.save()

            msg = (
                f"Кодовая база '{project_id}' успешно проиндексирована.\n"
                f"Найдено: {stats['files']} файлов, {stats['classes']} классов, {stats['functions']} функций.\n"
                f"Теперь его можно изучить подробнее с помощью соответствующих навыков."
            )
            system_logger.info(f"[Code Graph] Индексация '{project_id}' завершена.")
            return SkillResult.ok(msg)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Критическая ошибка при индексации: {e}")

    @skill(swarm_roles=[Subagents.CODER])
    async def delete_index(self, project_id: str) -> SkillResult:
        """
        Удаляет граф проекта из баз данных.
        """

        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(f"Индекс '{project_id}' не найден.")

        try:
            await self.graph.delete_project(project_id)
            await self.vector.delete_project(project_id)

            del self.client.state.active_indexes[project_id]
            self.client.state.save()
            return SkillResult.ok(f"Граф '{project_id}' успешно удален.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка удаления: {e}")

    # =========================================================================
    # Внутренняя синхронная логика парсинга
    # =========================================================================

    def _parse_and_build_sync(self, root_dir: Path, project_id: str) -> Dict[str, int]:
        """
        Синхронная обертка для CPU-bound задачи парсинга.
        """

        stats = {"files": 0, "classes": 0, "functions": 0}

        # Читаем игнорируемые папки из конфигурации
        exclude_dirs = set(self.client.config.exclude_dirs)

        # Собираем список Python файлов, игнорируя мусорные директории
        py_files = []
        for p in root_dir.rglob("*.py"):
            # Проверяем, пересекается ли путь файла с множеством исключенных папок
            if not set(p.parts).intersection(exclude_dirs):
                py_files.append(p)

        # 1-й проход: Создаем узлы (Файлы, Классы, Функции)
        # Мы используем asyncio.run() внутри потока - это допустимо, т.к. мы в отдельном Thread
        async def _process_nodes():
            for filepath in py_files:
                try:
                    rel_path = filepath.relative_to(root_dir).as_posix()
                    file_id = f"{project_id}::{rel_path}"

                    # Читаем исходник
                    source = filepath.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=str(filepath))

                    # Узел ФАЙЛА
                    await self.graph.upsert_node(
                        file_id, rel_path, "FILE", rel_path, project_id
                    )
                    stats["files"] += 1

                    # Парсим структуру
                    for node in tree.body:
                        # Если это КЛАСС
                        if isinstance(node, ast.ClassDef):
                            class_id = f"{file_id}::{node.name}"
                            await self.graph.upsert_node(
                                class_id, node.name, "CLASS", rel_path, project_id
                            )
                            await self.graph.link_nodes(file_id, class_id, "CONTAINS")
                            stats["classes"] += 1

                            docstring = ast.get_docstring(node)
                            if docstring:
                                await self.vector.save_doc(
                                    class_id, docstring, project_id, "CLASS"
                                )

                            # Ищем методы внутри класса
                            for item in node.body:
                                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    func_id = f"{class_id}.{item.name}"
                                    await self.graph.upsert_node(
                                        func_id, item.name, "FUNCTION", rel_path, project_id
                                    )
                                    await self.graph.link_nodes(class_id, func_id, "DEFINES")
                                    stats["functions"] += 1

                                    func_doc = ast.get_docstring(item)
                                    if func_doc:
                                        await self.vector.save_doc(
                                            func_id, func_doc, project_id, "FUNCTION"
                                        )

                        # Если это ФУНКЦИЯ вне класса
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            func_id = f"{file_id}::{node.name}"
                            await self.graph.upsert_node(
                                func_id, node.name, "FUNCTION", rel_path, project_id
                            )
                            await self.graph.link_nodes(file_id, func_id, "CONTAINS")
                            stats["functions"] += 1

                            func_doc = ast.get_docstring(node)
                            if func_doc:
                                await self.vector.save_doc(
                                    func_id, func_doc, project_id, "FUNCTION"
                                )

                except Exception as e:
                    system_logger.debug(f"[Code Graph] Ошибка парсинга {filepath.name}: {e}")

        # 2-й проход: Строим связи импортов
        # Для простоты: если в файле A есть `from B import C`, мы связываем файл A с файлом, который похож на B.
        async def _process_imports():
            file_ids = {p.relative_to(root_dir).as_posix() for p in py_files}

            for filepath in py_files:
                try:
                    rel_path = filepath.relative_to(root_dir).as_posix()
                    file_id = f"{project_id}::{rel_path}"
                    source = filepath.read_text(encoding="utf-8")
                    tree = ast.parse(source)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom) and node.module:
                            # Пытаемся угадать путь к файлу (например src.utils -> src/utils.py)
                            guessed_path = node.module.replace(".", "/") + ".py"
                            if guessed_path in file_ids:
                                target_id = f"{project_id}::{guessed_path}"
                                await self.graph.link_nodes(file_id, target_id, "IMPORTS")

                except Exception:
                    pass

        # Выполняем асинхронные задачи в нашем изолированном потоке
        new_loop = asyncio.new_event_loop()
        new_loop.run_until_complete(_process_nodes())
        new_loop.run_until_complete(_process_imports())
        new_loop.close()

        return stats
