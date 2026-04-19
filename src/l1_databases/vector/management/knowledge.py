import time
import uuid
from typing import Optional, TYPE_CHECKING, Any
from qdrant_client import models

from src.utils.dtime import format_timestamp
from src.utils.logger import system_logger

from src.l3_agent.skills.registry import skill, SkillResult

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel


class VectorKnowledge:
    """
    CRUD-функции для взаимодействия с коллекцией знаний агента.
    Здесь хранится неструктурированная информация (статьи, документация, факты из интернета).
    """

    def __init__(
        self,
        db: "VectorDB",
        embedding_model: "EmbeddingModel",
        collection: str = "knowledge",
        similarity_threshold: float = 0.65,
        timezone: int = 0,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.timezone = timezone

    def _format_time(self, timestamp: Optional[float]) -> str:
        if not timestamp:
            return "Неизвестно"
        return format_timestamp(timestamp, self.timezone)

    @skill()
    async def save_knowledge(self, knowledge_text: str) -> SkillResult:
        """Сохраняет фрагмент знаний."""

        if not self.db.client:
            return SkillResult.fail("Векторная БД не инициализирована.")

        try:
            vector = await self.embedding_model.get_embedding(knowledge_text)
            point_id = str(uuid.uuid4())

            # Сохраняем только текст и системное время
            payload = {"text": knowledge_text, "created_at": time.time()}

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            msg = f"[Vector DB] Знание успешно сохранено в базе данных (ID: {point_id})."
            # system_logger.info(msg) # Видно в Agent Action Result
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[Vector DB] Ошибка при сохранении знания в базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def search_knowledge(self, query: str, limit: int = 5) -> SkillResult:
        """Семантический поиск информации из базы данных."""

        try:
            # safe_query = query.replace("\n", " ").replace("\r", "")
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
                msg = "[Vector DB] Поиск знаний в базе данных не дал результатов."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            # system_logger.info(
            #     f"[Vector DB] База знаний вернула {len(points)} фрагментов по запросу '{safe_query}'."
            # )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")
                time_str = self._format_time(point.payload.get("created_at"))

                md_block = f"[ID: `{point.id}`][Время: {time_str}] Релевантность: {score}/{self.similarity_threshold}\n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при поиске знаний в базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def delete_knowledge(self, point_id: str) -> SkillResult:
        """Удаляет фрагмент знаний по ID."""
        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            msg = f"[Vector DB] Знание успешно удалено из базы данных (ID: {point_id})."
            system_logger.debug(msg)
            return SkillResult.ok(msg)
        except Exception as e:
            msg = f"[Vector DB] Ошибка при удалении знания из базы данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def get_all_knowledge(self, limit: int = 10) -> SkillResult:
        """Получает последние n записей из базы знаний (без семантического поиска)."""
        try:
            records, _ = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[Vector DB] База знаний пуста."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            system_logger.debug(
                f"[Vector DB] База данных выгрузила {len(records)} фрагментов знаний (чтение)."
            )

            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")
                time_str = self._format_time(point.payload.get("created_at"))

                md_block = f"[ID: `{point.id}`][Время: {time_str}]\n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при чтении базы знаний из базы данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)
