"""
Обёртка для поиска по векторной базе (Qdrant) в рамках механизма GraphRAG.
Скрывает в себе логику массовых (батчевых) запросов и дедупликации результатов.
"""

import asyncio
from typing import List, Dict, Any

from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts


class VectorSearchWrapper:
    """Утилита для стандартизированного поиска текстов в семантической БД."""

    def __init__(
        self,
        vector_knowledge: VectorKnowledge,
        vector_thoughts: VectorThoughts,
        top_k: int = 5,
    ) -> None:
        """
        Args:
            vector_knowledge: Контроллер базы знаний.
            vector_thoughts: Контроллер базы мыслей.
            top_k: Количество возвращаемых результатов на ОДИН поисковый вектор.
        """

        self.vector_knowledge = vector_knowledge
        self.vector_thoughts = vector_thoughts
        self.top_k = top_k

    async def search_batch(self, query_vectors: List[List[float]]) -> List[Dict[str, Any]]:
        """
        Выполняет параллельный семантический поиск по массиву векторов.
        Ищет одновременно в 'knowledge' и 'thoughts', объединяя и дедуплицируя результаты.

        Args:
            query_vectors: Массив сгенерированных эмбеддингов (тензоров).

        Returns:
            Список словарей вида:
            [
                {
                    "id": "uuid",
                    "text": "Полный текст воспоминания...",
                    "score": 0.89,
                    "collection": "knowledge",
                    "tags": ["domain:tech"]
                }, ...
            ]
        """
        if not query_vectors:
            return []

        # Формируем задачи (для каждого вектора ищем и в знаниях, и в мыслях)
        tasks = []
        for vector in query_vectors:
            # Ищем в базе знаний
            if self.vector_knowledge.db.client:
                tasks.append(
                    self.vector_knowledge.db.client.search(
                        collection_name=self.vector_knowledge.collection.name,
                        query_vector=vector,
                        limit=self.top_k,
                        score_threshold=self.vector_knowledge.similarity_threshold,
                        with_payload=True,
                    )
                )

            # Ищем в базе мыслей
            if self.vector_thoughts.db.client:
                tasks.append(
                    self.vector_thoughts.db.client.search(
                        collection_name=self.vector_thoughts.collection.name,
                        query_vector=vector,
                        limit=self.top_k,
                        score_threshold=self.vector_thoughts.similarity_threshold,
                        with_payload=True,
                    )
                )

        # Ждем выполнения всех запросов к Qdrant
        results_matrix = await asyncio.gather(*tasks, return_exceptions=True)

        # Сборка, дедупликация и форматирование результатов
        unique_points: Dict[str, Dict[str, Any]] = {}

        for i, search_result in enumerate(results_matrix):
            # Пропускаем ошибки или пустые результаты
            if isinstance(search_result, Exception) or not search_result:
                continue

            # Определяем, из какой коллекции пришел результат (задачи чередуются: 0-knowledge, 1-thoughts, 2-knowledge...)
            collection_name = "knowledge" if i % 2 == 0 else "thoughts"

            for point in search_result:
                point_id = str(point.id)
                score = float(point.score)
                text = point.payload.get("text", "")

                # Если такой ID уже находили - оставляем тот вариант, где Score выше
                if point_id in unique_points:
                    if score > unique_points[point_id]["score"]:
                        unique_points[point_id]["score"] = score
                else:
                    unique_points[point_id] = {
                        "id": point_id,
                        "text": text,
                        "score": score,
                        "collection": collection_name,
                        "tags": point.payload.get("tags", []),
                    }

        # Возвращаем плоский список всех найденных уникальных точек
        return list(unique_points.values())
