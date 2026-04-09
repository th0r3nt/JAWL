from typing import TYPE_CHECKING, Any, Dict
import uuid
from qdrant_client import models

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.collections import VectorCollection
    from src.l1_databases.vector.embedding import EmbeddingModel

from src.utils.logger import system_logger


class VectorThoughts:
    """
    CRUD-функции для взаимодействия с коллекцией мыслей агента.
    Рефлексия, мысли и консолидация.
    """

    def __init__(
        self,
        db: "VectorDB",
        collection: "VectorCollection",
        embedding_model: "EmbeddingModel",
        similarity_threshold: float = 0.43,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model

        self.similarity_threshold = similarity_threshold

    # @skill()
    async def save_thought(self, thought_text: str, metadata: Dict[str, Any] = None) -> str:
        """Сохраняет мысль агента."""
        try:
            vector = await self.embedding_model.get_embedding(thought_text)
            point_id = str(uuid.uuid4())  # Формируем уникальный ID
            payload = metadata or {}
            payload["text"] = thought_text

            # Сохраняем в векторную базу
            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            msg = f"[System] Мысль успешно сохранена в векторную базу данных (ID: {point_id})."
            system_logger.info(msg)
            return msg

        except Exception as e:
            msg = f"[System] Ошибка при сохранении мысли в векторную базу данных: {e}"
            system_logger.error(msg)
            return msg

    # @skill()
    async def search_thoughts(self, query: str, limit: int = 5) -> str:
        """Семантический поиск мыслей. Главный механизм "вспоминания" для агента."""
        try:
            query_vector = await self.embedding_model.get_embedding(query)

            # Используем новое API Qdrant
            search_result = await self.db.client.query_points(
                collection_name=self.collection.name,
                query=query_vector,
                limit=limit,
                score_threshold=self.similarity_threshold,
                with_payload=True,
            )

            # Универсальная обработка
            points = (
                search_result.points if hasattr(search_result, "points") else search_result
            )

            if not points:
                system_logger.info(
                    f"[System] Поиск мыслей в векторной базе данных по запросу '{query}' не дал результатов."
                )
                return "[System] Поиск мыслей в векторной базе данных не дал результатов."

            system_logger.info(
                f"[System] Векторная база данных вернула {len(points)} результатов по запросу '{query}'."
            )

            # Форматируем результат в удобный Markdown для LLM
            formatted_results = []
            for point in points:
                score = round(point.score, 2)  # Округляем для красоты
                text = point.payload.get("text", "")

                # Собираем метаданные в строку, если они есть
                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = f"\nМетаданные: `{metadata_dict}`" if metadata_dict else ""

                # Создаем Markdown-блок, используем реальный ID записи из БД
                md_block = (
                    f"[ID: `{point.id}`] Релевантность: {score}\n" f"{text}" f"{metadata_str}"
                )
                formatted_results.append(md_block)

            # Склеиваем все воспоминания через разделитель
            return "\n\n".join(formatted_results)

        except Exception as e:
            msg = f"[System] Ошибка при поиске мыслей в векторной базе данных: {e}"
            system_logger.error(msg)
            return msg

    # @skill()
    async def delete_thought(self, point_id: str):
        """Удаляет мысль по ID."""
        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[point_id]),
            )

            system_logger.info(
                f"[System] Мысль успешно удалена в векторной базе данных (ID: {point_id})."
            )
            return True

        except Exception as e:
            msg = f"[System] Ошибка при удалении мысли в векторной базе данных: {e}"
            system_logger.error(msg)
            return msg

    # @skill()
    async def get_all_thoughts(self, limit: int = 10) -> str:
        """Получает последние n мыслей из базы (без семантического поиска)."""
        try:
            # Используем scroll для простого чтения коллекции
            records, next_offset = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                with_payload=True,
                with_vectors=False,  # Вектора (массивы чисел) не нужны для текста
            )

            if not records:
                msg = "[System] Векторная коллекция мыслей пуста."
                system_logger.info(msg)
                return msg

            system_logger.info(
                f"[System] Векторная база данных выгрузила {len(records)} мыслей (чтение)."
            )

            # Форматируем результат в удобный Markdown для LLM
            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")

                # Собираем метаданные в строку, если они есть
                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = f"\nМетаданные: `{metadata_dict}`" if metadata_dict else ""

                # Создаем Markdown-блок (без score, т.к. это не поиск)
                md_block = f"[ID: `{point.id}`]\n" f"{text}" f"{metadata_str}"
                formatted_results.append(md_block)

            # Склеиваем все воспоминания через разделитель
            return "\n\n".join(formatted_results)

        except Exception as e:
            msg = f"[System] Ошибка при получении мыслей из векторной базы данных: {e}"
            system_logger.error(msg)
            return msg
