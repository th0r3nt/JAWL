"""
Семантический модуль для Матрицы Эйзенхауэра (Tasks).
Отвечает за группировку и форматирование задач в системном промпте.
"""

from typing import List, Dict
from src.utils.dtime import format_timestamp
from src.l1_databases.sql.tables import TaskTable

STATUS_EMOJIS = {
    "todo": "TODO",
    "in_progress": "IN_PROGRESS",
    "blocked": "BLOCKED",
    "done": "DONE",
    "cancelled": "CANCELLED",
}

QUADRANT_NAMES = {
    1: "Quadrant 1: urgent and important (DO FIRST)",
    2: "Quadrant 2: important, but not urgent (PLAN)",
    3: "Quadrant 3: urgent, but not important (DELEGATE)",
    4: "Quadrant 4: not urgent and not important (BACKLOG)",
}

ALLOWED_TAGS = [
    "priority:critical",
    "priority:high",
    "priority:low",
    "domain:research",
    "domain:code",
    "domain:os",
    "domain:social",
    "type:feature",
    "type:bugfix",
    "type:routine",
    "type:learning",
]


def build_eisenhower_matrix(tasks: List[TaskTable], max_tasks: int, tz_offset: int) -> str:
    """
    Формирует Markdown-представление матрицы Эйзенхауэра.
    """

    if not tasks:
        return f"## TASKS \nEisenhower Matrix. \nMax tasks allowed: {max_tasks}\nAllowed tags: {', '.join(ALLOWED_TAGS)}\n\nThe task list is empty."

    # Группируем задачи по квадрантам (по умолчанию 2, если что-то пошло не так)
    matrix: Dict[int, List[TaskTable]] = {1: [], 2: [], 3: [], 4: []}
    task_statuses = {t.id: t.status for t in tasks}

    for t in tasks:
        q = t.quadrant if t.quadrant in matrix else 2
        matrix[q].append(t)

    lines = [
        "## TASKS",
        "Eisenhower Matrix.",
        f"Max tasks allowed: {max_tasks}",
        f"Allowed tags: {', '.join(ALLOWED_TAGS)}",
    ]

    for q_num in range(1, 5):
        q_tasks = matrix[q_num]
        if not q_tasks:
            continue

        lines.append(f"\n[{QUADRANT_NAMES[q_num]}]")

        for t in q_tasks:
            status_icon = STATUS_EMOJIS.get(t.status, t.status.upper())
            lines.append(
                f"\n- [Task ID: `{t.id}`] {status_icon} | Progress: {t.progress}% | Title: {t.title}"
            )
            lines.append(f"  * Description: {t.description}")

            tags_str = f"[{', '.join(t.tags)}]" if t.tags else "None"
            deadline = (
                format_timestamp(t.due_date, tz_offset, "%Y-%m-%d %H:%M")
                if t.due_date
                else "None"
            )
            lines.append(f"  * Tags: {tags_str} | Deadline: {deadline}")

            if t.dependencies:
                deps_info = []
                for dep_id in t.dependencies:
                    d_stat = task_statuses.get(dep_id, "unknown")
                    if d_stat not in ("done", "cancelled", "unknown"):
                        deps_info.append(f"`{dep_id}` (Блокирует)")
                    else:
                        deps_info.append(f"`{dep_id}` (✓ {d_stat})")
                lines.append(f"  * Dependencies: {', '.join(deps_info)}")

            if t.subtasks:
                lines.append("  * Subtasks:")
                for sub in t.subtasks:
                    mark = "x" if sub.get("is_done") else " "
                    lines.append(f"    [{mark}] {sub.get('title', 'unknown')}")

            lines.append(f"  * Context: {t.context if t.context else 'Пусто'}")

    return "\n".join(lines).strip()
