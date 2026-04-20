import uuid
from typing import TYPE_CHECKING
from datetime import datetime, timezone
from sqlalchemy import select, func

from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.logger import system_logger
from src.utils.dtime import format_datetime
from src.l1_databases.sql.tables import DriveTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLDrives:
    """CRUD для управления внутренними потребностями (Drives) агента."""

    def __init__(
        self,
        db: "SQLDB",
        default_decay_rate: float = 2.5,
        max_history: int = 3,
        max_custom: int = 5,
        tz_offset: int = 0,
    ):
        self.db = db
        self.default_decay_rate = default_decay_rate
        self.max_history = max_history
        self.max_custom = max_custom
        self.tz_offset = tz_offset

    async def bootstrap_fundamental_drives(self):
        """Проверяет и создает базовые (фундаментальные) мотиваторы при запуске."""

        fundamental_drives = [
            {
                "name": "Curiosity",
                "description": "Потребность в расширении информационной базы. Инициирует поиск неизвестных концепций, анализ внешних источников и пополнение семантической памяти.",
            },
            {
                "name": "Social",
                "description": "Потребность в коммуникации. Направлена на обработку входящих запросов, поддержание активного статуса в каналах связи и проактивную инициализацию диалога для получения полезных социальных связей.",
            },
            {
                "name": "Mastery",
                "description": "Стремление к эффективности и порядку. Требует продвижения по долгосрочным задачам (TASKS), структурирования накопленных данных и проведения диагностики.",
            },
        ]

        async with self.db.session_factory() as session:
            for d in fundamental_drives:
                res = await session.execute(
                    select(DriveTable).where(DriveTable.name == d["name"])
                )
                if not res.scalar_one_or_none():
                    new_drive = DriveTable(
                        id=str(uuid.uuid4())[:8],
                        name=d["name"],
                        type="fundamental",
                        description=d["description"],
                        decay_rate=self.default_decay_rate,
                        last_satisfied_at=datetime.now(timezone.utc),
                        recent_reflections=[],
                    )
                    session.add(new_drive)
            await session.commit()

    @skill()
    async def satisfy_drive(self, drive_name: str, reflection_summary: str) -> SkillResult:
        """
        Сбрасывает дефицит мотиватора до 0%.
        Внимание: Вызывать строго вместе с фактическим действием, которое удовлетворяет этот драйв.
        reflection_summary: описание того, как именно была удовлетворена мотивация.
        """

        async with self.db.session_factory() as session:
            # Забираем все драйвы и ищем нужный на стороне Python (обход бага SQLite с кириллицей)
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

            drive = next((d for d in drives if d.name.lower() == drive_name.lower()), None)

            if not drive:
                return SkillResult.fail(f"Драйв '{drive_name}' не найден.")

            drive.last_satisfied_at = datetime.now(timezone.utc)

            time_str = format_datetime(drive.last_satisfied_at, self.tz_offset, "%m-%d %H:%M")
            entry = f"[{time_str}] {reflection_summary}"

            current_refs = list(drive.recent_reflections)
            current_refs.insert(0, entry)
            drive.recent_reflections = current_refs[: self.max_history]

            await session.commit()

        system_logger.info(f"[SQL DB] Дефицит драйва '{drive.name}' сброшен.")
        return SkillResult.ok(f"Дефицит драйва '{drive.name}' успешно сброшен до 0%.")

    @skill()
    async def create_custom_drive(
        self, name: str, description: str, decay_rate_per_hour: float = 2.5
    ) -> SkillResult:
        """Создает новую кастомную потребность/мотивацию."""

        async with self.db.session_factory() as session:
            count_res = await session.execute(
                select(func.count(DriveTable.id)).where(DriveTable.type == "custom")
            )
            if count_res.scalar_one() >= self.max_custom:
                return SkillResult.fail(
                    f"Достигнут лимит кастомных драйвов ({self.max_custom}). Удалите старые."
                )

            new_drive = DriveTable(
                id=str(uuid.uuid4())[:8],
                name=name,
                type="custom",
                description=description,
                decay_rate=decay_rate_per_hour,
                last_satisfied_at=datetime.now(timezone.utc),
                recent_reflections=[],
            )
            session.add(new_drive)
            await session.commit()

        system_logger.info(f"[SQL DB] Создан кастомный драйв '{name}'.")
        return SkillResult.ok(f"Кастомный драйв '{name}' успешно создан.")

    @skill()
    async def delete_custom_drive(self, drive_name: str) -> SkillResult:
        """Удаляет созданную кастомную потребность."""

        async with self.db.session_factory() as session:
            # Забираем все драйвы и ищем нужный на стороне Python
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

            drive = next((d for d in drives if d.name.lower() == drive_name.lower()), None)

            if not drive:
                return SkillResult.fail(f"Драйв '{drive_name}' не найден.")

            if drive.type == "fundamental":
                return SkillResult.fail(
                    "Отказано в доступе: Базовые (Fundamental) драйвы нельзя удалить."
                )

            await session.delete(drive)
            await session.commit()

        system_logger.info(f"[SQL DB] Удален кастомный драйв '{drive_name}'.")
        return SkillResult.ok(f"Драйв '{drive_name}' удален.")

    async def get_context_block(self, **kwargs) -> str:
        """Считает дефицит на лету и отдает блок контекста."""

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

        if not drives:
            return ""

        lines = [
            "## DRIVES \nДолгосрочные векторы поведения. Рекомендуется снижать дефицит, когда он высокий."
        ]
        now = datetime.now(timezone.utc)

        for d in drives:
            # Считаем дефицит на лету
            # Если tzinfo потерялся, восстанавливаем
            last_sat = (
                d.last_satisfied_at.replace(tzinfo=timezone.utc)
                if d.last_satisfied_at.tzinfo is None
                else d.last_satisfied_at
            )
            hours_passed = (now - last_sat).total_seconds() / 3600.0

            deficit = min(100.0, hours_passed * d.decay_rate)
            deficit_int = int(deficit)

            # Эмодзи статуса
            if deficit_int >= 80:
                status = "Высокий"
            elif deficit_int >= 40:
                status = "Растет"
            else:
                status = "В норме"

            lines.append(f"\n[{d.type.upper()}] {d.name}")
            lines.append(f"* Дефицит: {deficit_int}/100 {status}")
            lines.append(f"* Описание: {d.description}")

            if d.recent_reflections:
                lines.append("* История удовлетворения:")
                for ref in d.recent_reflections:
                    lines.append(f"  - {ref}")
            else:
                lines.append("* История удовлетворения: Пусто")

        return "\n".join(lines)
