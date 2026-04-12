from typing import Optional, TYPE_CHECKING, Any, Dict
import uuid
from qdrant_client import models

from src.utils.logger import system_logger

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel

from src.l3_agent.skills.registry import skill, SkillResult


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
        similarity_threshold: float = 0.45,
    ):
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold

    @skill()
    async def save_knowledge(
        self, knowledge_text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """Сохраняет фрагмент знаний."""
        if not self.db.client:
            return SkillResult.fail("Векторная БД не инициализирована.")

        try:
            vector = await self.embedding_model.get_embedding(knowledge_text)
            point_id = str(uuid.uuid4())
            payload = metadata or {}
            payload["text"] = knowledge_text

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            )

            msg = (
                f"[System] Знание успешно сохранено в векторной базе данных (ID: {point_id})."
            )
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[System] Ошибка при сохранении знания в векторной базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def search_knowledge(self, query: str, limit: int = 5) -> SkillResult:
        """Семантический поиск информации. Главный механизм поиска фактов для агента."""
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
                msg = "[System] Поиск знаний в векторной базе данных не дал результатов."
                system_logger.info(msg)
                return SkillResult.ok(msg)

            system_logger.info(
                f"[System] Векторная база знаний вернула {len(points)} фрагментов знаний по запросу '{query}'."
            )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")

                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = (
                    f"\nМетаданные (источник): `{metadata_dict}`" if metadata_dict else ""
                )

                md_block = f"[ID: `{point.id}`] Релевантность: {score}\n{text}{metadata_str}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[System] Ошибка при поиске знаний в векторной базе данных: {e}"
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

            msg = f"[System] Знание успешно удалено из векторной базы данных (ID: {point_id})."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[System] Ошибка при удалении знания из векторной базы данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill()
    async def get_all_knowledge(self, limit: int = 10) -> SkillResult:
        """Получает последние n записей из базы знаний (без семантического поиска)."""
        try:
            records, next_offset = await self.db.client.scroll(
                collection_name=self.collection.name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[System] База знаний пуста."
                system_logger.info(msg)
                return SkillResult.ok(msg)

            system_logger.info(
                f"[System] ВБД выгрузила {len(records)} фрагментов знаний (чтение)."
            )

            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")
                metadata_dict = {k: v for k, v in point.payload.items() if k != "text"}
                metadata_str = (
                    f"\nМетаданные (источник): `{metadata_dict}`" if metadata_dict else ""
                )

                md_block = f"[ID: `{point.id}`]\n{text}{metadata_str}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[System] Ошибка при чтении базы знаний из векторной базы данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)
