"""
Обёртка для поиска по графовой базе данных (KuzuDB) в рамках механизма GraphRAG.
Обеспечивает безопасное извлечение узлов и их соседей (neighborhood) с защитой
от "взрыва" связей.
"""

import json
import asyncio
from typing import List, Dict, Any

from src.utils.logger import system_logger
from src.l1_databases.graph.manager import GraphManager
from src.l1_databases.graph.schema import GRAPH_NODE_TABLE, GRAPH_EDGE_TABLES


class GraphSearchWrapper:
    """Утилита для стандартизированного поиска в графе знаний."""

    def __init__(self, graph_manager: GraphManager, max_neighbors: int = 15) -> None:
        """
        Args:
            graph_manager: Менеджер графовой БД.
            max_neighbors: Жесткий лимит на количество вытаскиваемых соседей
                           для одного узла (защита от огромных узлов).
        """

        self.graph = graph_manager
        self.max_neighbors = max_neighbors

    async def get_all_node_names(self) -> List[str]:
        """
        Выгружает имена всех существующих узлов графа.
        Необходимо для построения словаря Aho-Corasick (FlashText).
        """

        if not self.graph.db.conn:
            return []

        def _fetch_names() -> List[str]:
            names = []
            try:
                res = self.graph.db.conn.execute(f"MATCH (n:{GRAPH_NODE_TABLE}) RETURN n.name")
                while res.has_next():
                    names.append(res.get_next()[0])
            except Exception as e:
                system_logger.error(f"[GraphRAG] Ошибка получения узлов графа: {e}")
            return names

        # Запускаем в отдельном потоке, так как KuzuDB может блокировать GIL
        return await asyncio.to_thread(_fetch_names)

    async def get_nodes_with_neighborhood(self, node_names: List[str]) -> List[Dict[str, Any]]:
        """
        Для списка имен узлов извлекает их собственные данные (описания) и данные
        связанных с ними соседних узлов.

        Args:
            node_names: Список точных имен узлов (якорей).

        Returns:
            Список словарей вида:
            [
                {
                    "name": "Docker",
                    "description": "Система контейнеризации...",
                    "category": "SOFTWARE",
                    "relations": [
                        "-[REQUIRES]-> (Linux)",
                        "<-[PART_OF]- от (Server_1)"
                    ]
                }, ...
            ]
        """
        
        if not self.graph.db.conn or not node_names:
            return []

        def _fetch_neighborhood() -> List[Dict[str, Any]]:
            results = []

            for name in node_names:
                # Защита от Cypher Injection через json.dumps
                safe_name = json.dumps(name, ensure_ascii=False)

                try:
                    # 1. Забираем сам узел
                    node_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.description, n.category, n.is_active"
                    res = self.graph.db.conn.execute(node_q)

                    if not res.has_next():
                        continue

                    row = res.get_next()
                    # Обязательно сбрасываем итератор
                    while res.has_next():
                        res.get_next()

                    desc, cat, is_active = row[0], row[1], row[2]

                    # Пропускаем заархивированные узлы
                    if not is_active:
                        continue

                    node_data = {
                        "name": name,
                        "description": desc,
                        "category": cat,
                        "relations": [],
                    }

                    # 2. Ищем соседей по всем типам связей (Ограничиваем LIMIT, чтобы не вытащить полбазы)
                    for rel in GRAPH_EDGE_TABLES:
                        # Исходящие связи
                        q_out = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})-[e:{rel}]->(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name LIMIT {self.max_neighbors}"
                        res_out = self.graph.db.conn.execute(q_out)
                        while res_out.has_next():
                            target = res_out.get_next()[0]
                            node_data["relations"].append(f"-[{rel}]-> ({target})")

                        # Входящие связи
                        q_in = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})<-[e:{rel}]-(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name LIMIT {self.max_neighbors}"
                        res_in = self.graph.db.conn.execute(q_in)
                        while res_in.has_next():
                            source = res_in.get_next()[0]
                            node_data["relations"].append(f"<-[{rel}]- от ({source})")

                    results.append(node_data)

                except Exception as e:
                    system_logger.error(
                        f"[GraphRAG] Ошибка извлечения соседей для '{name}': {e}"
                    )

            return results

        # Выполняем синхронные Cypher-запросы в потоке, чтобы не блочить Event Loop
        async with self.graph.db.write_lock:  # На всякий случай берем лок базы
            return await asyncio.to_thread(_fetch_neighborhood)
