# Файл: src/l1_databases/vector/management/thoughts.py

from typing import Optional, TYPE_CHECKING, Any, Dict
import uuid
from qdrant_client import models

from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.logger import system_logger

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel


class VectorThoughts:
    """
    CRUD-функции для взаимодействия с коллекцией мыслей агента.
    Рефлексия, мысли и консолидация.
    """

    def __init__(
        self,
        db: "VectorDB",
        embedding_model: "EmbeddingModel",
        collection: str = "thoughts",
        similarity_threshold: float = 0.43,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold

    @skill()
    async def save_thought(
        self, thought_text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """Сохраняет мысль в векторную базу данных."""
        try:
            vector = await self.embedding_model.get_embedding(thought_text)
            point_id = str(uuid.uuid4())  # Формируем уникальный ID
            payload = metadata or {}
            payload["text"] = thought_text

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            msg = f"[System] Мысль успешно сохранена в векторную базу данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[System] Ошибка при сохранении мысли в векторную базу данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def search_thoughts(self, query: str, limit: int = 5) -> SkillResult:
        """Семантический поиск мыслей из векторной базы данных."""
        try:
            query_vector = await self.embedding_model.get_embedding(query)

            search_result = await self.db.client.query_points(
                collection_name=self.collection.name,
                query=query_vector,
                limit=limit,
                score_threshold=self.similarity_threshold,
                with_payload=True,
            )

            points: list[Any] = (
                search_result.points if hasattr(search_result, "points") else search_result
            )

            if not points:
                msg = f"[System] Поиск мыслей в векторной базе данных по запросу '{query}' не дал результатов."
                system_logger.info(msg)
                return SkillResult.ok(msg)

            system_logger.info(
                f"[System] Векторная база данных вернула {len(points)} результатов по запросу '{query}'."
            )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")

                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = f"\nМетаданные: `{metadata_dict}`" if metadata_dict else ""

                md_block = f"[ID: `{point.id}`] Релевантность: {score}\n{text}{metadata_str}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[System] Ошибка при поиске мыслей в векторной базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def delete_thought(self, point_id: str) -> SkillResult:
        """Удаляет мысль из векторной базы данных по ID."""
        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[point_id]),
            )

            msg = f"[System] Мысль успешно удалена в векторной базе данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[System] Ошибка при удалении мысли в векторной базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def get_all_thoughts(self, limit: int = 10) -> SkillResult:
        """Получает последние n мыслей из векторной базы данных."""
        try:
            records, next_offset = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[System] Векторная коллекция мыслей пуста."
                system_logger.info(msg)
                return SkillResult.ok(msg)

            system_logger.info(
                f"[System] Векторная база данных выгрузила {len(records)} мыслей (чтение)."
            )

            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")

                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = f"\nМетаданные: `{metadata_dict}`" if metadata_dict else ""

                md_block = f"[ID: `{point.id}`]\n{text}{metadata_str}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[System] Ошибка при получении мыслей из векторной базы данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)
