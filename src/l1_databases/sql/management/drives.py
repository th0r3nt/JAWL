import uuid
from typing import TYPE_CHECKING
from datetime import datetime, timezone, timedelta
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
        decay_rate: float = 2.5,
        decay_interval_sec: int = 3600,
        max_history: int = 3,
        max_custom: int = 5,
        tz_offset: int = 0,
    ):
        self.db = db
        self.decay_rate = decay_rate
        self.decay_interval_sec = decay_interval_sec
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
                "description": "Потребность в коммуникации. Направлена на обработку входящих запросов, поддержание активного статуса в каналах связи и проактивную инициализацию диалога.",
            },
            {
                "name": "Mastery",
                "description": "Стремление к эффективности и порядку. Требует продвижения по долгосрочным задачам (TASKS), структурирования данных и диагностики.",
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
                        decay_rate=self.decay_rate,
                        last_satisfied_at=datetime.now(timezone.utc),
                        recent_reflections=[],
                    )
                    session.add(new_drive)
            await session.commit()

    @skill()
    async def satisfy_drive(
        self, drive_name: str, amount: int, reflection_summary: str
    ) -> SkillResult:
        """
        Снижает показатель дефицита мотиватора на указанную величину.
        amount: от 1 до 100 (на сколько процентов закрыта потребность).
        reflection_summary: описание того, как именно была удовлетворена мотивация.

        Маловажные действия: рекомендуется 5-15.
        Средние действия: 15-30.
        Важные, сложные действия: 30-60.
        """

        amount = max(1, min(100, amount))

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

            drive = next((d for d in drives if d.name.lower() == drive_name.lower()), None)

            if not drive:
                return SkillResult.fail(f"Драйв '{drive_name}' не найден.")

            now = datetime.now(timezone.utc)
            last_sat = (
                drive.last_satisfied_at.replace(tzinfo=timezone.utc)
                if drive.last_satisfied_at.tzinfo is None
                else drive.last_satisfied_at
            )

            # Высчитываем текущий дефицит
            intervals_passed = (now - last_sat).total_seconds() / self.decay_interval_sec
            current_deficit = min(100.0, intervals_passed * drive.decay_rate)

            # Считаем новый дефицит после удовлетворения
            new_deficit = max(0.0, current_deficit - amount)

            # Высчитываем время, когда дефицит был бы равен new_deficit
            seconds_ago = (new_deficit / drive.decay_rate) * self.decay_interval_sec
            drive.last_satisfied_at = now - timedelta(seconds=seconds_ago)

            time_str = format_datetime(now, self.tz_offset, "%m-%d %H:%M")
            entry = f"[{time_str}] Снижен на {amount}%: {reflection_summary}"

            current_refs = list(drive.recent_reflections)
            current_refs.insert(0, entry)
            drive.recent_reflections = current_refs[: self.max_history]

            await session.commit()

        system_logger.debug(f"[SQL DB] Дефицит драйва '{drive.name}' снижен на {amount}%.")
        return SkillResult.ok(
            f"Дефицит драйва '{drive.name}' успешно снижен на {amount}%. Текущий остаток: {int(new_deficit)}/100"
        )

    @skill()
    async def create_custom_drive(
        self, name: str, description: str, decay_rate: float = 2.5
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
                decay_rate=decay_rate,
                last_satisfied_at=datetime.now(timezone.utc),
                recent_reflections=[],
            )
            session.add(new_drive)
            await session.commit()

        system_logger.debug(f"[SQL DB] Создан кастомный драйв '{name}'.")
        return SkillResult.ok(f"Кастомный драйв '{name}' успешно создан.")

    @skill()
    async def delete_custom_drive(self, drive_name: str) -> SkillResult:
        """Удаляет созданную кастомную потребность."""

        async with self.db.session_factory() as session:
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

        system_logger.debug(f"[SQL DB] Удален кастомный драйв '{drive_name}'.")
        return SkillResult.ok(f"Драйв '{drive_name}' удален.")

    async def get_context_block(self, **kwargs) -> str:
        """Считает дефицит на лету и отдает блок контекста."""

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

        if not drives:
            return ""

        lines = [
            "## DRIVES \nДолгосрочные векторы поведения. Рекомендуется снижать дефицит, когда он высокий.",
            f"Длительность 1 интервала: {self.decay_interval_sec} сек.",
            f"Лимит кастомных мотиваций: {self.max_custom}",
        ]

        now = datetime.now(timezone.utc)

        for d in drives:
            last_sat = (
                d.last_satisfied_at.replace(tzinfo=timezone.utc)
                if d.last_satisfied_at.tzinfo is None
                else d.last_satisfied_at
            )

            intervals_passed = (now - last_sat).total_seconds() / self.decay_interval_sec
            deficit = min(100.0, intervals_passed * d.decay_rate)
            deficit_int = int(deficit)

            if deficit_int >= 90:
                status = "(Критический дефицит: приоритетная задача)"

            elif deficit_int >= 70:
                status = "(Высокий: требует внимания)"

            elif deficit_int >= 50:
                status = "(Растет: рекомендуется запланировать действия)"

            elif deficit_int >= 30:
                status = "(Лёгкий дефицит: не критично)"

            else:
                status = "(В норме: потребность удовлетворена)"

            lines.append(f"\n[{d.type.upper()}] {d.name}")
            lines.append(f"* Дефицит: {deficit_int}/100 {status}")
            lines.append(f"* Рост дефицита: +{d.decay_rate}% за 1 интервал")
            lines.append(f"* Описание: {d.description}")

            if d.recent_reflections:
                lines.append("* История удовлетворения:")
                for ref in d.recent_reflections:
                    # Жестко режем длинные рефлексии
                    limit = 500
                    short_ref = ref if len(ref) <= limit else ref[:limit] + "... [Обрезано системой]"
                    lines.append(f"  - {short_ref}")
            else:
                lines.append("* История удовлетворения: Пусто")

        return "\n".join(lines)
