# Файл: C:\Users\ivanc\Desktop\JAWL\src\l1_databases\vector\management\knowledge.py

from typing import TYPE_CHECKING, Any, Dict
import uuid
from qdrant_client import models

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.collections import VectorCollection
    from src.l1_databases.vector.embedding import EmbeddingModel

from src.utils.logger import system_logger


class VectorKnowledge:
    """
    CRUD-функции для взаимодействия с коллекцией знаний агента.
    Здесь хранится неструктурированная информация (статьи, документация, факты из интернета).
    """

    def __init__(
        self,
        db: "VectorDB",
        collection: "VectorCollection",
        embedding_model: "EmbeddingModel",
        similarity_threshold: float = 0.45,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model

        self.similarity_threshold = similarity_threshold

    # @skill()
    async def save_knowledge(
        self, knowledge_text: str, metadata: Dict[str, Any] = None
    ) -> str:
        """Сохраняет фрагмент знаний."""
        try:
            vector = await self.embedding_model.get_embedding(knowledge_text)
            point_id = str(uuid.uuid4())
            payload = metadata or {}
            payload["text"] = knowledge_text

            # Сохраняем в векторную базу
            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            msg = (
                f"[System] Знание успешно сохранено в векторной базе данных (ID: {point_id})."
            )
            system_logger.info(msg)
            return msg

        except Exception as e:
            msg = f"[System] Ошибка при сохранении знания в векторной базе данных: {e}"
            system_logger.error(msg)
            return msg

    # @skill()
    async def search_knowledge(self, query: str, limit: int = 5) -> str:
        """Семантический поиск информации. Главный механизм поиска фактов для агента."""
        try:
            query_vector = await self.embedding_model.get_embedding(query)

            # Используем новое API Qdrant (query_points вместо search)
            search_result = await self.db.client.query_points(
                collection_name=self.collection.name,
                query=query_vector,
                limit=limit,
                score_threshold=self.similarity_threshold,  # Отсекаем мусор
                with_payload=True,  # Просим БД вернуть текст и метаданные
            )

            # Универсальная обработка (вытаскиваем массив точек)
            points = (
                search_result.points if hasattr(search_result, "points") else search_result
            )

            if not points:
                system_logger.info(
                    f"[System] Поиск знаний по запросу '{query}' в векторной базе данных не дал результатов."
                )
                return "[System] Поиск знаний в векторной базе данных не дал результатов."

            system_logger.info(
                f"[System] Векторная база знаний вернула {len(points)} фрагментов знаний по запросу '{query}'."
            )

            # Форматируем результат в удобный Markdown для LLM
            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")

                # Собираем метаданные в строку (например, url источника, дата)
                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = (
                    f"\nМетаданные (источник): `{metadata_dict}`" if metadata_dict else ""
                )

                # Создаем Markdown-блок, используем реальный ID записи из БД
                md_block = (
                    f"[ID: `{point.id}`] Релевантность: {score}\n" f"{text}" f"{metadata_str}"
                )
                formatted_results.append(md_block)

            # Склеиваем все найденные фрагменты
            return "\n\n".join(formatted_results)

        except Exception as e:
            msg = f"[System] Ошибка при поиске знаний в векторной базе данных: {e}"
            system_logger.error(msg)
            return msg

    # @skill()
    async def delete_knowledge(self, point_id: str):
        """Удаляет фрагмент знаний по ID."""
        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[point_id]),
            )

            system_logger.info(
                f"[System] Знание успешно удалено из векторной базы данных (ID: {point_id})."
            )
            return True

        except Exception as e:
            msg = f"[System] Ошибка при удалении знания из векторной базы данных: {e}"
            system_logger.error(msg)
            return msg

    # @skill()
    async def get_all_knowledge(self, limit: int = 10) -> str:
        """Получает последние n записей из базы знаний (без семантического поиска)."""
        try:
            # Используем scroll для простого чтения коллекции
            records, next_offset = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[System] База знаний пуста."
                system_logger.info(msg)
                return msg

            system_logger.info(
                f"[System] ВБД выгрузила {len(records)} фрагментов знаний (чтение)."
            )

            # Форматируем результат в удобный Markdown для LLM
            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")
                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = (
                    f"\nМетаданные (источник): `{metadata_dict}`" if metadata_dict else ""
                )

                # Создаем Markdown-блок
                md_block = f"[ID: `{point.id}`]\n" f"{text}" f"{metadata_str}"
                formatted_results.append(md_block)

            return "\n\n".join(formatted_results)

        except Exception as e:
            msg = f"[System] Ошибка при чтении базы знаний из векторной базы данных: {e}"
            system_logger.error(msg)
            return msg
