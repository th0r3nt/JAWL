import time
import uuid
from typing import TYPE_CHECKING, Any
from qdrant_client import models

from src.utils.dtime import safe_format_timestamp
from src.utils.logger import system_logger
from src.utils._tools import truncate_text  # <--- Добавили

from src.l3_agent.skills.registry import skill, SkillResult

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel


class VectorThoughts:
    def __init__(
        self,
        db: "VectorDB",
        embedding_model: "EmbeddingModel",
        collection: str = "thoughts",
        similarity_threshold: float = 0.65,
        timezone: int = 0,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.timezone = timezone

        self.session_ignored_ids = set()

    def clear_session_cache(self):
        """Очищает игнор-лист текущего ReAct-цикла."""
        self.session_ignored_ids.clear()

    @skill()
    async def save_thought(self, thought_text: str) -> SkillResult:
        """Сохраняет мысль в базу данных."""

        try:
            vector = await self.embedding_model.get_embedding(thought_text)
            point_id = str(uuid.uuid4())

            payload = {"text": thought_text, "created_at": time.time()}

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            self.session_ignored_ids.add(point_id)  # <--- Прячем от самого себя

            msg = f"[Vector DB] Мысль успешно сохранена в базу данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[Vector DB] Ошибка при сохранении мысли: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def search_thoughts(self, query: str, limit: int = 5) -> SkillResult:
        """Семантический поиск мыслей из базы данных."""

        try:
            query_vector = await self.embedding_model.get_embedding(query)

            query_filter = None
            if self.session_ignored_ids:
                query_filter = models.Filter(
                    must_not=[models.HasIdCondition(has_id=list(self.session_ignored_ids))]
                )

            search_result = await self.db.client.query_points(
                collection_name=self.collection.name,
                query=query_vector,
                limit=limit,
                score_threshold=self.similarity_threshold,
                query_filter=query_filter,
                with_payload=True,
            )

            points: list[Any] = (
                search_result.points if hasattr(search_result, "points") else search_result
            )

            if not points:
                msg = "[Vector DB] Поиск мыслей не дал результатов."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            short_query = truncate_text(query.replace("\n", " "), 200, "... [Обрезано]")
            system_logger.info(
                f"[Vector DB] Мысли: найдено {len(points)} записей по запросу '{short_query}'"
            )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")
                time_str = safe_format_timestamp(
                    point.payload.get("created_at"), self.timezone
                )

                md_block = f"[ID: `{point.id}`] [Время: {time_str}] Релевантность: {score}/{self.similarity_threshold}\n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при поиске мыслей: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def delete_thought(self, point_id: str) -> SkillResult:
        """Удаляет мысль из базы данных по ID."""

        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            msg = f"[Vector DB] Мысль успешно удалена в базе данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)
        except Exception as e:
            msg = f"[Vector DB] Ошибка при удалении мысли: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def get_all_thoughts(self, limit: int = 10) -> SkillResult:
        """Получает последние n мыслей из базы данных."""

        try:
            scroll_filter = None
            if self.session_ignored_ids:
                scroll_filter = models.Filter(
                    must_not=[models.HasIdCondition(has_id=list(self.session_ignored_ids))]
                )

            records, _ = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                scroll_filter=scroll_filter,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[Vector DB] Векторная коллекция мыслей пуста."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")
                time_str = safe_format_timestamp(
                    point.payload.get("created_at"), self.timezone
                )

                md_block = f"[ID: `{point.id}`] [Время: {time_str}]\n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при получении мыслей: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)
