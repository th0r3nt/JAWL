"""
CRUD controller of the Personality Traits table.

Allows the agent to dynamically adapt to the user: store
behavioral patterns, preferred response formats, and individual rules.
"""

import uuid
from typing import Optional, TYPE_CHECKING, Any
from sqlalchemy import select, delete, func

from src.utils.logger import main_logger

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.subconscious.schema import Pattern

from src.l1_databases.sql.tables import PersonalityTraitTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLPersonalityTraits:
    """CRUD for managing acquired personality traits of the agent."""

    def __init__(self, db: "SQLDB", max_traits: int = 10) -> None:
        """
        Initializes the personality traits controller.

        Args:
            db: Connection to SQLite.
            max_traits: Maximum number of stored traits in memory.
        """
        self.db = db
        self.max_traits = max_traits

    @skill(subconscious=[Pattern.REFLECTION])
    async def add_trait(
        self,
        name: str,
        description: str,
        reason: Optional[str] = None,
        context: Optional[str] = None,
    ) -> SkillResult:
        """
        Adds new acquired personality trait.

        reason: Triggering event for this trait.
        context: Situations where this trait applies.
        """

        # Truncate IDs to fit typical short schemas
        trait_id = str(uuid.uuid4())[:8]

        async with self.db.session_factory() as session:
            # Check limits
            count_res = await session.execute(select(func.count(PersonalityTraitTable.id)))
            if count_res.scalar_one() >= self.max_traits:
                return SkillResult.fail(
                    f"Maximum limit of acquired personality traits reached ({self.max_traits}). "
                    "It is recommended to delete obsolete ones."
                )

            new_trait = PersonalityTraitTable(
                id=trait_id, name=name, description=description, reason=reason, context=context
            )
            session.add(new_trait)
            await session.commit()

        return SkillResult.ok(f"True. ID: {trait_id}")

    @skill(subconscious=[Pattern.REFLECTION])
    async def get_traits(self) -> SkillResult:
        """
        Returns list of all acquired personality traits.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(select(PersonalityTraitTable))
            traits = result.scalars().all()

        if not traits:
            return SkillResult.ok("Acquired personality traits list is empty.")

        lines = []
        for t in traits:
            lines.append(f"['{t.name}'] (ID: `{t.id}`)")
            lines.append(f"* Description: {t.description}")
            if t.reason:
                lines.append(f"* Reason: {t.reason}")
            if t.context:
                lines.append(f"* Context: {t.context}")
            lines.append("")  # Empty line separator

        return SkillResult.ok("\n".join(lines).strip())

    @skill(subconscious=[Pattern.REFLECTION])
    async def remove_trait(self, trait_id: str) -> SkillResult:
        """
        Deletes personality trait by ID.
        """
        async with self.db.session_factory() as session:
            result = await session.execute(
                delete(PersonalityTraitTable).where(PersonalityTraitTable.id == trait_id)
            )
            await session.commit()

            if result.rowcount == 0:
                return SkillResult.fail(f"Personality trait with ID {trait_id} not found.")

        msg = f"Personality trait {trait_id} deleted."
        main_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        Returns a formatted block for the agent's context.
        """

        res = await self.get_traits()
        return f"## PERSONALITY TRAITS\nMax traits allowed: {self.max_traits}\n\n{res.message}"
