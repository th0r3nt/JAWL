"""
CRUD-контроллер для таблицы Notes (Рабочие заметки).

Обеспечивает агента оперативной памятью ("стикерами на мониторе").
Эти заметки всегда висят в системном промпте, что позволяет не терять
важные промежуточные данные между далекими ReAct-циклами.
"""

import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import select, delete, func

from src.utils.logger import system_logger
from src.utils.dtime import format_datetime
from src.utils._tools import truncate_text

from src.l1_databases.sql.tables import NoteTable

from src.l3_agent.skills.registry import skill, SkillResult

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLNotes:
    """Контроллер оперативных заметок (Working Memory)."""

    def __init__(self, db: "SQLDB", max_notes: int = 5, tz_offset: int = 0) -> None:
        """
        Инициализирует контроллер заметок.

        Args:
            db: Подключение к SQLite.
            max_notes: Максимальное количество активных заметок.
            tz_offset: Смещение временной зоны.
        """

        self.db = db
        self.max_notes = max_notes
        self.tz_offset = tz_offset

    @skill()
    async def add_note(self, content: str) -> SkillResult:
        """
        Создает новую оперативную заметку.
        Заметка будет всегда отображаться в системном контексте периферийным зрением.
        Полезно для хранения эфемерных To-Do списков, промежуточных ID, портов, заметок или неструктурированных идей на будущее.

        Args:
            content: Текст заметки.
        """

        if not content or not content.strip():
            return SkillResult.fail("Ошибка: Текст заметки не может быть пустым.")

        note_id = str(uuid.uuid4())[:8]

        async with self.db.session_factory() as session:
            count_res = await session.execute(select(func.count(NoteTable.id)))
            if count_res.scalar_one() >= self.max_notes:
                return SkillResult.fail(
                    f"Достигнут лимит заметок ({self.max_notes}). Рекомендуется удалить старые перед созданием новой."
                )

            new_note = NoteTable(id=note_id, content=content.strip())
            session.add(new_note)
            await session.commit()

        msg = f"Заметка успешно создана (ID: {note_id})."
        system_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def update_note(self, note_id: str, content: str) -> SkillResult:
        """
        Полностью перезаписывает текст существующей заметки по её ID.

        Args:
            note_id: ID редактируемой заметки.
            content: Новый текст заметки.
        """
        if not content or not content.strip():
            return SkillResult.fail("Ошибка: Текст заметки не может быть пустым.")

        async with self.db.session_factory() as session:
            result = await session.execute(select(NoteTable).where(NoteTable.id == note_id))
            note = result.scalar_one_or_none()

            if not note:
                return SkillResult.fail(f"Заметка с ID '{note_id}' не найдена.")

            note.content = content.strip()
            # updated_at обновится автоматически благодаря onupdate в таблице
            await session.commit()

        msg = f"Заметка '{note_id}' успешно обновлена."
        system_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def delete_note(self, note_id: str) -> SkillResult:
        """
        Удаляет заметку по её ID. Обязательно вызвать, когда данные теряют актуальность.

        Args:
            note_id: ID удаляемой заметки.
        """
        async with self.db.session_factory() as session:
            result = await session.execute(delete(NoteTable).where(NoteTable.id == note_id))
            await session.commit()

            if result.rowcount == 0:
                return SkillResult.fail(f"Заметка с ID '{note_id}' не найдена.")

        msg = f"Заметка '{note_id}' удалена."
        system_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def list_all_notes(self) -> SkillResult:
        """
        Читает полное содержимое всех текущих заметок.
        Полезно, если в системном промпте текст длинной заметки был обрезан.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(
                select(NoteTable).order_by(NoteTable.updated_at.desc())
            )
            notes = result.scalars().all()

        if not notes:
            return SkillResult.ok("Список заметок пуст.")

        lines = ["Заметки:"]
        for note in notes:
            time_str = format_datetime(note.updated_at, self.tz_offset, "%Y-%m-%d %H:%M")
            lines.append(f"\n--- [ID: {note.id}] (Обновлено: {time_str}) ---")
            lines.append(note.content)

        return SkillResult.ok("\n".join(lines))

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Отдает отформатированный блок контекста для системного промпта.
        Длинные заметки обрезаются, чтобы не выжигать окно токенов.
        """
        async with self.db.session_factory() as session:
            result = await session.execute(
                select(NoteTable).order_by(NoteTable.updated_at.desc())
            )
            notes = result.scalars().all()

        if not notes:
            return ""

        lines = [f"## NOTES [Лимит: {self.max_notes}]\n"]
        for note in notes:
            time_str = format_datetime(note.updated_at, self.tz_offset, "%H:%M")
            content = note.content.replace("\n", "  ")

            # Используем нашу глобальную утилиту для обрезки
            content = truncate_text(
                content,
                max_chars=500,
                suffix="... [Обрезано]",
            )

            lines.append(f"- `[{note.id}]` ({time_str}): {content}")

        return "\n".join(lines).strip()
