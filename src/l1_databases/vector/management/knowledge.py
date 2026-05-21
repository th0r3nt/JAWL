"""
CRUD controller for the 'knowledge' collection (Knowledge Base).

Stores long-term, objective facts from the external world (documentation, read articles, lore).
Supports similarity search with strict tag filtering.
"""

import time
import uuid
from typing import TYPE_CHECKING, Any, Literal, List, Optional
from qdrant_client import models

from src.utils.dtime import safe_format_timestamp
from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents
from src.l3_agent.subconscious.schema import Pattern

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel
    from src.l1_databases.vector.collections import VectorCollection

# Strictly predefined list of tags for classification
VectorTag = Literal[
    # Knowledge domains
    "domain:tech",  # Technical information
    "domain:lore",  # Lore regarding subjects/objects
    "domain:self",  # Self information/architecture
    # Knowledge types
    "type:fact",  # Strict facts
    "type:concept",  # Abstract knowledge
    "type:rule",  # Core rules
    # Knowledge retention
    "retention:core",  # Fundamental
    "retention:ephemeral",  # Short-term/ephemeral
]

ReliabilityLevel = Literal["verified", "assumption", "untrusted"]


class VectorKnowledge:
    """Agent interface to the objective knowledge base."""

    def __init__(
        self,
        db: "VectorDB",
        embedding_model: "EmbeddingModel",
        collection: "VectorCollection",
        similarity_threshold: float = 0.65,
        timezone: int = 0,
    ) -> None:
        """
        Initializes the knowledge controller.

        Args:
            db: Connection to Qdrant.
            embedding_model: FastEmbed vector synthesizer.
            collection: Reference to the collection.
            similarity_threshold: Cosine similarity threshold (Cosine Distance).
            timezone: Timezone offset.
        """
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.timezone = timezone

    @skill(
        swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.CONSOLIDATION, Pattern.FORGETTING]
    )
    async def save_knowledge(
        self,
        knowledge_text: str,
        tags: List[VectorTag],
        source: str,
        reliability: ReliabilityLevel = "verified",
    ) -> SkillResult:
        """
        Vectorizes and saves knowledge snippet to database.

        source: Origin of the fact.
        reliability: level of trustworthiness.
        """

        if not tags:
            return SkillResult.fail("Error: You must specify at least one tag from the list.")

        if not self.db.client:
            return SkillResult.fail("Vector DB is not initialized.")

        try:
            vector = await self.embedding_model.get_embedding(str(knowledge_text))
            point_id = str(uuid.uuid4())

            payload = {
                "text": str(knowledge_text),
                "created_at": time.time(),
                "tags": tags,
                "source": source,
                "reliability": reliability,
            }

            await self.db.client.upsert(
                collection_name=self.collection.name,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
                wait=True,
            )

            msg = f"[Vector DB] Knowledge successfully saved to the database (ID: {point_id}). Tags: {tags}"
            main_logger.info(msg)
            return SkillResult.ok(f"True. ID: {point_id}")

        except Exception as e:
            msg = f"[Vector DB] Error saving knowledge to the database: {e}"
            main_logger.error(msg)
            return SkillResult.fail(msg)

    @skill(
        swarm=[Subagents.ARCHIVIST],
        subconscious=[Pattern.CONSOLIDATION, Pattern.REFLECTION, Pattern.FORGETTING],
    )
    async def search_knowledge(
        self, query: str, limit: int = 5, tags_filter: Optional[List[VectorTag]] = None
    ) -> SkillResult:
        """
        Performs semantic search over saved knowledge.

        tags_filter: Optional. Returns only facts containing all specified tags.
        """

        try:
            query_str = str(query)
            query_vector = await self.embedding_model.get_embedding(query_str)

            # Build filter (Logical AND - all specified tags must match)
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
                msg = "[Vector DB] Knowledge search returned no results."
                main_logger.debug(msg)
                return SkillResult.ok("Knowledge search returned no results.")

            short_query = truncate_text(query_str.replace("\n", " "), 50, "... [Truncated]")
            main_logger.info(
                f"[Vector DB] Knowledge: found {len(points)} records for query '{short_query}'"
            )

            formatted_results = []
            for point in points:
                score = round(point.score, 2)
                text = point.payload.get("text", "")

                # Protection against corrupted data in the DB itself (from past hallucinations)
                point_tags = point.payload.get("tags", [])
                if isinstance(point_tags, str):
                    point_tags = [point_tags]
                elif not isinstance(point_tags, list):
                    point_tags = [str(point_tags)]

                tags_str = (
                    f"[{', '.join(str(t) for t in point_tags)}]" if point_tags else "[No tags]"
                )
                time_str = safe_format_timestamp(
                    point.payload.get("created_at"), self.timezone
                )

                source = point.payload.get("source", "Not specified")
                reliability = point.payload.get("reliability", "verified")

                md_block = f"[ID: `{point.id}`] \n[Time: {time_str}] \n[Source: {source}] \n[Reliability: {reliability}] \n[Tags: {tags_str}] \n[Relevance: {score}/{self.similarity_threshold}] \n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Error searching knowledge: {e}"
            main_logger.error(msg)
            return SkillResult.fail(msg)

    @skill(
        swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.FORGETTING, Pattern.CONSOLIDATION]
    )
    async def delete_knowledge(self, point_id: str) -> SkillResult:
        """
        Deletes knowledge snippet.
        """
        try:
            await self.db.client.delete(
                collection_name=self.collection.name,
                points_selector=models.PointIdsList(points=[str(point_id)]),
                wait=True,
            )
            msg = f"[Vector DB] Knowledge successfully deleted from the database (ID: {point_id})."
            main_logger.debug(msg)
            return SkillResult.ok(msg)

        except Exception as e:
            msg = f"[Vector DB] Error deleting knowledge: {e}"
            main_logger.error(msg)
            return SkillResult.fail(msg)

    @skill(
        swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.FORGETTING, Pattern.CONSOLIDATION]
    )
    async def get_all_knowledge(
        self, limit: int = 50, tags_filter: Optional[List[VectorTag]] = None
    ) -> SkillResult:
        """
        Retrieves last N records from knowledge base.
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
                msg = "[Vector DB] Knowledge base is empty (or there are no records with specified tags)."
                main_logger.debug(msg)
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
                    f"[{', '.join(str(t) for t in point_tags)}]" if point_tags else "[No tags]"
                )
                time_str = safe_format_timestamp(
                    point.payload.get("created_at"), self.timezone
                )

                source = point.payload.get("source", "Not specified")
                reliability = point.payload.get("reliability", "verified")

                md_block = f"[ID: `{point.id}`] \n[Time: {time_str}] \n[Source: {source}] \n[Reliability: {reliability}] \n[Tags: {tags_str}] \n{text}"
                formatted_results.append(md_block)

            return SkillResult.ok("\n\n".join(formatted_results))

        except Exception as e:
            msg = f"[Vector DB] Error reading knowledge base: {e}"
            main_logger.error(msg)
            return SkillResult.fail(msg)
