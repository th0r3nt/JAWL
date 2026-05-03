"""
CRUD-контроллер для работы с графом знаний (Knowledge Graph).

Реализует навыки добавления концепций и их связывания.
Включает магию Entity Resolution (нечеткий поиск) и идемпотентные запросы,
защищенные от багов парсера KuzuDB через сериализацию литералов (json.dumps).
"""

import asyncio
import json
from typing import List, Optional
from rapidfuzz import process, fuzz

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l1_databases.graph.db import GraphDB
from src.l1_databases.graph.schema import (
    GRAPH_NODE_TABLE,
    GRAPH_EDGE_TABLES,
    RelationType,
    ConceptCategory,
)


class GraphCRUD:
    """Интерфейс агента к графовой базе знаний."""

    def __init__(self, db: GraphDB, max_nodes: int = 5000) -> None:
        self.db = db
        self.max_nodes = max_nodes

    def _get_all_names(self) -> List[str]:
        """Возвращает имена всех существующих узлов в графе."""
        if not self.db.conn:
            return []

        res = self.db.conn.execute(f"MATCH (n:{GRAPH_NODE_TABLE}) RETURN n.name")
        names = []
        while res.has_next():
            names.append(res.get_next()[0])
        return names

    def _fuzzy_match(self, entity_name: str, threshold: float = 85.0) -> str:
        """
        Магия Entity Resolution: ищет похожее имя узла в графе.
        Если находит с совпадением > threshold, возвращает существующее имя.
        Если нет — возвращает исходное (будет создан новый узел).
        """
        existing_nodes = self._get_all_names()
        if not existing_nodes:
            return entity_name.strip()

        # Используем processor, чтобы сравнивать строки в нижнем регистре.
        # Это спасет от боли, когда "Docker" и "docker" дают скор 83.3% и не проходят порог 85%
        match = process.extractOne(
            entity_name.strip(), 
            existing_nodes, 
            processor=lambda x: x.lower() if isinstance(x, str) else x,
            scorer=fuzz.WRatio
        )

        if match:
            best_name, score, _ = match
            if score >= threshold:
                system_logger.debug(
                    f"[Graph DB] Fuzzy Match: '{entity_name}' -> '{best_name}' (Score: {score:.1f})"
                )
                return best_name

        return entity_name.strip()

    @skill(swarm_roles=[Subagents.ARCHIVIST, Subagents.WEB_RESEARCHER])
    async def add_concept(
        self, name: str, description: str, category: ConceptCategory = "CONCEPT"
    ) -> SkillResult:
        """
        Добавляет новый узел или обновляет существующий (Upsert).

        Args:
            name: Имя концепции, субъекта или объекта.
            description: Что это такое.
            category: Строго из списка категорий.
        """
        async with self.db.write_lock:

            def _sync_manage() -> str:
                # Резолвим имя (порог 85 - стандарт для Upsert)
                resolved_name = self._fuzzy_match(name, threshold=85.0)

                # Бронебойная защита от Cypher Injection и багов парсера Kuzu
                safe_name = json.dumps(resolved_name, ensure_ascii=False)
                safe_desc = json.dumps(description, ensure_ascii=False)
                safe_cat = json.dumps(category, ensure_ascii=False)

                check_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.name"
                res = self.db.conn.execute(check_q)
                exists = res.has_next()

                # Обязательно потребляем итератор, чтобы KuzuDB сняла Read Lock с записи!
                while res.has_next():
                    res.get_next()

                if exists:
                    # Обновляем. Добавляем RETURN, чтобы KuzuDB гарантированно зафиксировала SET
                    update_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) SET n.description = {safe_desc}, n.category = {safe_cat}, n.is_active = true RETURN n.name"
                    res_upd = self.db.conn.execute(update_q)
                    while res_upd.has_next():
                        res_upd.get_next()
                else:
                    # Создаем. Добавляем RETURN
                    create_q = f"CREATE (n:{GRAPH_NODE_TABLE} {{name: {safe_name}, description: {safe_desc}, category: {safe_cat}, is_active: true}}) RETURN n.name"
                    res_crt = self.db.conn.execute(create_q)
                    while res_crt.has_next():
                        res_crt.get_next()

                return resolved_name

            try:
                final_name = await asyncio.to_thread(_sync_manage)
                msg = f"Концепт '{final_name}' (Тип: {category}) сохранен в граф."
                system_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok(msg)
            except Exception as e:
                return SkillResult.fail(f"Ошибка БД: {e}")

    @skill(swarm_roles=[Subagents.ARCHIVIST, Subagents.WEB_RESEARCHER])
    async def link_concepts(
        self, source_name: str, target_name: str, relation: RelationType, description: str = ""
    ) -> SkillResult:
        """
        Создает связь между двумя узлами. Если узлов нет — они создаются автоматически.

        Args:
            source_name: Имя исходящего узла.
            target_name: Имя целевого узла.
            relation: Тип связи (строго из списка).
            description: Описание связи (почему они связаны).
        """
        if relation not in GRAPH_EDGE_TABLES:
            return SkillResult.fail(f"Неизвестный тип связи: {relation}")

        async with self.db.write_lock:

            def _sync_link() -> str:
                src = self._fuzzy_match(source_name, threshold=85.0)
                tgt = self._fuzzy_match(target_name, threshold=85.0)

                safe_src = json.dumps(src, ensure_ascii=False)
                safe_tgt = json.dumps(tgt, ensure_ascii=False)
                safe_desc = json.dumps(description, ensure_ascii=False)

                # Гарантируем существование узлов
                for n_name, s_name in [(src, safe_src), (tgt, safe_tgt)]:
                    res = self.db.conn.execute(
                        f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {s_name}}}) RETURN n.name"
                    )
                    exists = res.has_next()
                    while res.has_next():
                        res.get_next()

                    if not exists:
                        res_crt = self.db.conn.execute(
                            f"CREATE (n:{GRAPH_NODE_TABLE} {{name: {s_name}, is_active: true}}) RETURN n.name"
                        )
                        while res_crt.has_next():
                            res_crt.get_next()

                # Проверяем дубликаты
                check_q = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}})-[e:{relation}]->(b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}}) RETURN e"
                res = self.db.conn.execute(check_q)
                has_edge = res.has_next()
                while res.has_next():
                    res.get_next()

                if not has_edge:
                    create_q = f"""
                    MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}}), (b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}})
                    CREATE (a)-[e:{relation} {{description: {safe_desc}}}]->(b)
                    RETURN e.description
                    """
                    res_edge = self.db.conn.execute(create_q)
                    while res_edge.has_next():
                        res_edge.get_next()

                return f"({src}) -[{relation}]-> ({tgt})"

            try:
                link_str = await asyncio.to_thread(_sync_link)
                msg = f"Связь обновлена: {link_str}"
                system_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok(msg)
            except Exception as e:
                return SkillResult.fail(f"Ошибка связывания: {e}")

    @skill(swarm_roles=[Subagents.ARCHIVIST, Subagents.WEB_RESEARCHER])
    async def get_concept_neighborhood(self, name: str) -> SkillResult:
        """
        Ищет узел и возвращает все его связи.
        """

        def _sync_explore() -> str:
            # Порог 75 для более агрессивного поиска при запросах
            resolved_name = self._fuzzy_match(name, threshold=75.0)
            safe_name = json.dumps(resolved_name, ensure_ascii=False)

            res = self.db.conn.execute(
                f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.description, n.category, n.is_active"
            )
            if not res.has_next():
                return f"Узел, похожий на '{name}', не найден в графе."

            row = res.get_next()
            # Очищаем результат (снимаем блокировку)
            while res.has_next():
                res.get_next()

            desc, cat, is_active = row[0], row[1], row[2]

            if not is_active:
                return f"Концепт '{resolved_name}' был заархивирован."

            lines = [f"### Концепт: {resolved_name} (Тип: {cat})\nОписание: {desc}\n\nСвязи:"]
            found_edges = False

            # Ищем связи по всем таблицам отношений
            for rel in GRAPH_EDGE_TABLES:
                # ИСХОДЯЩИЕ
                q_out = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})-[e:{rel}]->(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name, e.description"
                res_out = self.db.conn.execute(q_out)
                while res_out.has_next():
                    found_edges = True
                    r = res_out.get_next()
                    e_desc = f" ({r[1]})" if r[1] else ""
                    lines.append(f"  -[{rel}]-> ({r[0]}){e_desc}")

                # ВХОДЯЩИЕ
                q_in = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})<-[e:{rel}]-(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name, e.description"
                res_in = self.db.conn.execute(q_in)
                while res_in.has_next():
                    found_edges = True
                    r = res_in.get_next()
                    e_desc = f" ({r[1]})" if r[1] else ""
                    lines.append(f"  <-[{rel}]- от ({r[0]}){e_desc}")

            if not found_edges:
                lines.append("  (Изолированный узел, активных связей нет)")

            return "\n".join(lines)

        try:
            report = await asyncio.to_thread(_sync_explore)
            return SkillResult.ok(report)
        except Exception as e:
            return SkillResult.fail(f"Ошибка исследования графа: {e}")

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def remove_link(
        self, source_name: str, target_name: str, relation: Optional[RelationType] = None
    ) -> SkillResult:
        """
        Удаляет связь(и) между двумя узлами.
        Если relation не передан, удаляются все связи между этими узлами.
        """
        async with self.db.write_lock:

            def _sync_remove_link() -> str:
                # Порог 95%, чтобы не удалить случайно созвучную связь
                src = self._fuzzy_match(source_name, threshold=95.0)
                tgt = self._fuzzy_match(target_name, threshold=95.0)

                safe_src = json.dumps(src, ensure_ascii=False)
                safe_tgt = json.dumps(tgt, ensure_ascii=False)

                rels_to_check = [relation] if relation else GRAPH_EDGE_TABLES

                for rel in rels_to_check:
                    # KuzuDB не поддерживает удаление ненаправленных ребер, поэтому удаляем в обе стороны явно с RETURN
                    q_out = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}})-[e:{rel}]->(b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}}) DELETE e RETURN a.name"
                    res_out = self.db.conn.execute(q_out)
                    while res_out.has_next():
                        res_out.get_next()

                    q_in = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}})<-[e:{rel}]-(b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}}) DELETE e RETURN a.name"
                    res_in = self.db.conn.execute(q_in)
                    while res_in.has_next():
                        res_in.get_next()

                return f"Связи между '{src}' и '{tgt}' удалены."

            try:
                msg = await asyncio.to_thread(_sync_remove_link)
                system_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok(msg)
            except Exception as e:
                return SkillResult.fail(f"Ошибка удаления связи: {e}")

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def erase_concept(self, name: str) -> SkillResult:
        """
        Полностью стирает узел и его связи из базы данных.
        """
        async with self.db.write_lock:

            def _sync_erase() -> str:
                # Порог 95%, чтобы случайно не снести полбазы
                resolved_name = self._fuzzy_match(name, threshold=95.0)
                safe_name = json.dumps(resolved_name, ensure_ascii=False)

                check_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.name"
                res = self.db.conn.execute(check_q)
                exists = res.has_next()
                while res.has_next():
                    res.get_next()

                if not exists:
                    return f"Узел '{name}' не найден."

                # Сначала выжигаем все связи явно в обе стороны
                for rel in GRAPH_EDGE_TABLES:
                    res_e1 = self.db.conn.execute(
                        f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}})-[e:{rel}]->() DELETE e RETURN n.name"
                    )
                    while res_e1.has_next():
                        res_e1.get_next()

                    res_e2 = self.db.conn.execute(
                        f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}})<-[e:{rel}]-() DELETE e RETURN n.name"
                    )
                    while res_e2.has_next():
                        res_e2.get_next()

                # Теперь удаляем сам узел
                res_del = self.db.conn.execute(
                    f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) DELETE n RETURN n.name"
                )
                while res_del.has_next():
                    res_del.get_next()

                return f"Узел '{resolved_name}' и все его связи физически уничтожены."

            try:
                msg = await asyncio.to_thread(_sync_erase)
                system_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok(msg)
            except Exception as e:
                return SkillResult.fail(f"Ошибка жесткого удаления: {e}")

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def archive_concept(self, name: str) -> SkillResult:
        """
        Мягкое удаление. Скрывает узел из поиска и графа связей, но оставляет в базе.
        """
        async with self.db.write_lock:

            def _sync_archive() -> bool:
                resolved_name = self._fuzzy_match(name, threshold=95.0)
                safe_name = json.dumps(resolved_name, ensure_ascii=False)

                res = self.db.conn.execute(
                    f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) SET n.is_active = false RETURN n.name"
                )
                exists = res.has_next()
                while res.has_next():
                    res.get_next()
                return exists

            try:
                success = await asyncio.to_thread(_sync_archive)
                if success:
                    return SkillResult.ok(f"Концепт '{name}' заархивирован.")
                return SkillResult.fail(f"Концепт '{name}' не найден.")
            except Exception as e:
                return SkillResult.fail(f"Ошибка при архивации: {e}")
