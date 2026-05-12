"""
Семантический модуль для Mental States.
Отвечает за красивую группировку сущностей, их отношений (Attitude) и связей.
"""

from typing import List
from datetime import datetime, timezone
from src.l1_databases.sql.tables import MentalStateTable


def build_mental_states(states: List[MentalStateTable], max_entities: int) -> str:
    if not states:
        return f"## MENTAL STATES\nMax number of entities that can be remembered: {max_entities}\n\nСписок сущностей пуст."

    lines = [
        "## MENTAL STATES",
        f"Max number of entities that can be remembered: {max_entities}\n",
    ]

    for s in states:
        updated_at_aware = (
            s.updated_at.replace(tzinfo=timezone.utc)
            if s.updated_at.tzinfo is None
            else s.updated_at
        )
        delta = datetime.now(timezone.utc) - updated_at_aware
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        time_ago = f"{hours}h {minutes}m ago"

        tier_str = s.tier.upper()
        # Иконки для понимания "одушевленности"

        lines.append(
            f"[{s.category.capitalize()}: {s.name}] (ID: `{s.id}` | Tier: {tier_str} | Updated: {time_ago})"
        )
        lines.append(f"  * Description: {s.description}")
        lines.append(f"  * Status: {s.status}")

        if s.attitude and s.attitude.lower() != "neutral":
            lines.append(f"  * Attitude: {s.attitude}")

        if s.directives:
            lines.append(f"  * Directives: {s.directives}")

        if s.epistemic_state:
            lines.append(f"  * Epistemic State, Theory of Mind: {s.epistemic_state}")

        if s.context:
            lines.append(f"  * Context: {s.context}")

        if s.related_information:
            lines.append(f"  * Related Info: {s.related_information}")

        if s.relations:
            lines.append("  * Relations:")
            for rel_id, rel_desc in s.relations.items():
                lines.append(f"    -> [ID: {rel_id}]: {rel_desc}")

        lines.append("")  # Отступ между карточками

    return "\n".join(lines).strip()
