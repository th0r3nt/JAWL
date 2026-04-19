import time
import uuid
from typing import Optional, TYPE_CHECKING, Any, Dict
from qdrant_client import models

from src.utils.dtime import format_timestamp
from src.utils.logger import system_logger

from src.l3_agent.skills.registry import skill, SkillResult

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
        timezone: int = 0,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.timezone = timezone

    def _format_time(self, timestamp: Optional[float]) -> str:
        """Вспомогательный метод для красивого вывода времени."""
        if not timestamp:
            return "Неизвестно"
        return format_timestamp(timestamp, self.timezone)

    @skill()
    async def save_thought(
        self, thought_text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """Сохраняет мысль в векторную базу данных."""

        try:
            vector = await self.embedding_model.get_embedding(thought_text)
            point_id = str(uuid.uuid4())
            payload = metadata or {}
            payload["text"] = thought_text

            # Добавляем метку времени, если ее нет
            if "created_at" not in payload:
                payload["created_at"] = time.time()

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            msg = f"[Vector DB] Мысль успешно сохранена в базу данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[Vector DB] Ошибка при сохранении мысли в базу данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def search_thoughts(self, query: str, limit: int = 5) -> SkillResult:
        """Семантический поиск мыслей из векторной базы данных."""

        try:
            safe_query = query.replace("\n", " ").replace("\r", "")
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
                msg = f"[Vector DB] Поиск мыслей в базе данных по запросу '{safe_query}' не дал результатов."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            system_logger.info(
                f"[Vector DB] База данных вернула {len(points)} мыслей по запросу '{safe_query}'."
            )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")
                time_str = self._format_time(point.payload.get("created_at"))

                metadata_dict = {
                    k: v for k, v in point.payload.items() if k not in ("text", "created_at")
                }
                metadata_str = f"\nМетаданные: `{metadata_dict}`" if metadata_dict else ""

                md_block = f"[ID: `{point.id}`] [Время: {time_str}] Релевантность: {score}/{self.similarity_threshold}\n{text}{metadata_str}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при поиске мыслей в базе данных: {e}"
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
            msg = f"[Vector DB] Мысль успешно удалена в базе данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[Vector DB] Ошибка при удалении мысли в базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def get_all_thoughts(self, limit: int = 10) -> SkillResult:
        """Получает последние n мыслей из векторной базы данных."""

        try:
            records, _ = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[Vector DB] Векторная коллекция мыслей пуста."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            system_logger.debug(
                f"[Vector DB] База данных выгрузила {len(records)} мыслей (чтение)."
            )

            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")
                time_str = self._format_time(point.payload.get("created_at"))

                metadata_dict = {
                    k: v for k, v in point.payload.items() if k not in ("text", "created_at")
                }
                metadata_str = f"\nМетаданные: `{metadata_dict}`" if metadata_dict else ""

                md_block = f"[ID: `{point.id}`] [Время: {time_str}]\n{text}{metadata_str}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при получении мыслей из базы данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)
