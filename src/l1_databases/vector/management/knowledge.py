"""
CRUD-контроллер для коллекции 'knowledge' (База знаний).

Хранит долгосрочные, объективные факты из внешнего мира (документация, прочитанные статьи, лор).
Поддерживает поиск по схожести (similarity search) с жесткой фильтрацией по тегам.
"""

import time
import uuid
from typing import TYPE_CHECKING, Any, Literal, List, Optional
from qdrant_client import models

from src.utils.dtime import safe_format_timestamp
from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel
    from src.l1_databases.vector.collections import VectorCollection

# Жестко заданный список тегов для классификации
VectorTag = Literal[
    # Домены знаний
    "domain:tech",  # Техническая инфа
    "domain:lore",  # Инфа про субъектов
    "domain:self",  # Инфа про себя
    # Типы знаний
    "type:fact",  # Строгие факты
    "type:concept",  # Абстрактные знания
    "type:rule",  # Правила поведения
    # Длительность знаний
    "retention:core",  # Фундаментально
    "retention:ephemeral",  # Временно
]


class VectorKnowledge:
    """Интерфейс агента к базе объективных знаний."""

    def __init__(
        self,
        db: "VectorDB",
        embedding_model: "EmbeddingModel",
        collection: "VectorCollection",
        similarity_threshold: float = 0.65,
        timezone: int = 0,
    ) -> None:
        """
        Инициализирует контроллер знаний.

        Args:
            db: Подключение к Qdrant.
            embedding_model: Синтезатор векторов FastEmbed.
            collection: Ссылка на коллекцию.
            similarity_threshold: Порог косинусного сходства (Cosine Distance).
            timezone: Смещение часового пояса.
        """
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.timezone = timezone

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def save_knowledge(self, knowledge_text: str, tags: List[VectorTag]) -> SkillResult:
        """
        Векторизует и сохраняет фрагмент знаний в базу.

        Args:
            knowledge_text: Текстовый блок информации для запоминания.
            tags: Строгий список тегов для будущей жесткой фильтрации при RAG.
        """

        if not tags:
            return SkillResult.fail("Ошибка: Необходимо указать хотя бы один тег из списка.")

        if not self.db.client:
            return SkillResult.fail("Векторная БД не инициализирована.")

        try:
            vector = await self.embedding_model.get_embedding(str(knowledge_text))
            point_id = str(uuid.uuid4())

            payload = {"text": str(knowledge_text), "created_at": time.time(), "tags": tags}

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
                wait=True,
            )

            msg = f"[Vector DB] Знание успешно сохранено в базе данных (ID: {point_id}). Теги: {tags}"
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[Vector DB] Ошибка при сохранении знания в базе данных: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def search_knowledge(
        self, query: str, limit: int = 5, tags_filter: Optional[List[VectorTag]] = None
    ) -> SkillResult:
        """
        Выполняет семантический поиск по сохраненным знаниям.

        Args:
            query: Текстовый запрос (будет конвертирован в вектор).
            limit: Максимальное количество возвращаемых релевантных узлов.
            tags_filter: Опциональный фильтр. Отсекает факты, не содержащие ВСЕ указанные теги.
        """

        try:
            query_str = str(query)
            query_vector = await self.embedding_model.get_embedding(query_str)

            # Строим фильтр (Логическое И - должны совпасть все переданные теги)
            query_filter = None
            if tags_filter:
                if isinstance(tags_filter, str):
                    tags_filter = [tags_filter]
                elif not isinstance(tags_filter, list):
                    tags_filter = [str(tags_filter)]

                must_conditions = [
                    models.FieldCondition(key="tags", match=models.MatchValue(value=str(tag)))
                    for tag in tags_filter
                ]
                query_filter = models.Filter(must=must_conditions)

            search_result = await self.db.client.query_points(
                collection_name=self.collection.name,
                query=query_vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=self.similarity_threshold,
                with_payload=True,
            )

            points: list[Any] = (
                search_result.points if hasattr(search_result, "points") else search_result
            )

            if not points:
                msg = "[Vector DB] Поиск знаний не дал результатов."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            short_query = truncate_text(query_str.replace("\n", " "), 50, "... [Обрезано]")
            system_logger.info(
                f"[Vector DB] Знания: найдено {len(points)} записей по запросу '{short_query}'"
            )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")

                # Защита от битых данных в самой БД (от прошлых галлюцинаций)
                point_tags = point.payload.get("tags", [])
                if isinstance(point_tags, str):
                    point_tags = [point_tags]
                elif not isinstance(point_tags, list):
                    point_tags = [str(point_tags)]

                tags_str = (
                    f"[{', '.join(str(t) for t in point_tags)}]"
                    if point_tags
                    else "[Без тегов]"
                )
                time_str = safe_format_timestamp(
                    point.payload.get("created_at"), self.timezone
                )

                md_block = f"[ID: `{point.id}`] [Время: {time_str}] {tags_str} Релевантность: {score}/{self.similarity_threshold}\n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при поиске знаний: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def delete_knowledge(self, point_id: str) -> SkillResult:
        """
        Безвозвратно удаляет фрагмент знаний по его ID.

        Args:
            point_id: Идентификатор узла (возвращается при поиске).
        """
        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[str(point_id)]),
                wait=True,
            )
            msg = f"[Vector DB] Знание успешно удалено из базы данных (ID: {point_id})."
            system_logger.debug(msg)
            return SkillResult.ok(msg)
        except Exception as e:
            msg = f"[Vector DB] Ошибка при удалении знания: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)

    @skill(swarm_roles=[Subagents.ARCHIVIST])
    async def get_all_knowledge(
        self, limit: int = 50, tags_filter: Optional[List[VectorTag]] = None
    ) -> SkillResult:
        """
        Получает последние N записей из базы знаний (с возможной фильтрацией по тегам).
        Используется субагентами (ARCHIVIST) для масштабной ревизии памяти.

        Args:
            limit: Сколько записей извлечь.
            tags_filter: Опциональный массив тегов.
        """
        try:
            query_filter = None
            if tags_filter:
                if isinstance(tags_filter, str):
                    tags_filter = [tags_filter]
                elif not isinstance(tags_filter, list):
                    tags_filter = [str(tags_filter)]

                must_conditions = [
                    models.FieldCondition(key="tags", match=models.MatchValue(value=str(tag)))
                    for tag in tags_filter
                ]
                query_filter = models.Filter(must=must_conditions)

            records, _ = await self.db.client.scroll(
                collection_name=self.collection.name,
                scroll_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                msg = "[Vector DB] База знаний пуста (или нет записей с указанными тегами)."
                system_logger.debug(msg)
                return SkillResult.ok(msg)

            formatted_results = []
            for point in records:
                text = point.payload.get("text", "")

                point_tags = point.payload.get("tags", [])
                if isinstance(point_tags, str):
                    point_tags = [point_tags]
                elif not isinstance(point_tags, list):
                    point_tags = [str(point_tags)]

                tags_str = (
                    f"[{', '.join(str(t) for t in point_tags)}]"
                    if point_tags
                    else "[Без тегов]"
                )
                time_str = safe_format_timestamp(
                    point.payload.get("created_at"), self.timezone
                )

                md_block = f"[ID: `{point.id}`] [Время: {time_str}] {tags_str}\n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Ошибка при чтении базы знаний: {e}"
            system_logger.error(msg)
            return SkillResult.fail(msg)
