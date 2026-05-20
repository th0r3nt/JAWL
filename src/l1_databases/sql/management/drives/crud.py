"""
CRUD-контроллер для управления внутренними потребностями (Drives) агента.

Реализует математическую модель роста дефицита от 0% до 100% с течением времени.
Позволяет агенту проактивно выполнять задачи в моменты "скуки".
"""

import uuid
from typing import TYPE_CHECKING, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, desc, text

from src.utils.logger import main_logger
from src.utils.dtime import format_datetime

from src.l1_databases.sql.tables import DriveTable, TickTable
from src.l1_databases.sql.management.drives.semantics import DRIVES_SEMANTIC_MATRIX

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB

from src.l3_agent.skills.registry import skill, SkillResult


class SQLDrives:
    """CRUD для управления внутренними потребностями (Drives) агента."""

    def __init__(
        self,
        db: "SQLDB",
        dynamic_reduction: bool = True,
        pause_on_offline: bool = True,
        max_history: int = 3,
        max_custom: int = 5,
        tz_offset: int = 0,
        fundamental_config: dict = None,
    ) -> None:
        """
        Инициализирует контроллер мотиваторов.

        Args:
            db: Подключение к SQLite.
            max_history: Лимит хранимых рефлексий на один драйв.
            max_custom: Максимальное количество кастомных (созданных агентом) драйвов.
            tz_offset: Смещение временной зоны.
            fundamental_config: конфигурации (скорости и состояния) базовых драйвов.
        """

        self.db = db

        self.dynamic_reduction = dynamic_reduction
        self.pause_on_offline = pause_on_offline

        self.max_history = max_history
        self.max_custom = max_custom
        self.fundamental_config = fundamental_config or {}

        self.tz_offset = tz_offset

    async def bootstrap_migrations(self) -> None:
        """Мягкая миграция для добавления колонки decay_interval_sec в старые БД."""
        async with self.db.engine.begin() as conn:
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE drives ADD COLUMN decay_interval_sec INTEGER DEFAULT 3600"
                    )
                )
                main_logger.info(
                    "[SQL DB] Выполнена успешная миграция таблицы Drives (добавлен decay_interval_sec)."
                )
            except Exception as e:
                main_logger.debug(
                    f"[SQL DB] Миграция таблицы Drives пропущена (возможно, колонка уже существует): {e}"
                )

    async def bootstrap_fundamental_drives(self) -> None:
        """
        Синхронизирует базовые (system-level) мотиваторы с БД на основе настроек YAML.
        Если драйв включен, но его нет - создает. Если выключен, но есть - удаляет.
        """
        fundamental_defs = {
            "curiosity": {
                "name": "Curiosity",
                "description": "Потребность в расширении информационной базы. Инициирует поиск неизвестных концепций, анализ внешних источников и пополнение семантической памяти.",
            },
            "social": {
                "name": "Social",
                "description": "Потребность в коммуникации. Направлена на обработку входящих запросов, поддержание активного статуса в каналах связи и проактивную инициализацию диалога.",
            },
            "mastery": {
                "name": "Mastery",
                "description": "Стремление к эффективности и порядку. Требует продвижения по долгосрочным задачам (TASKS), структурирования данных и диагностики.",
            },
        }

        async with self.db.session_factory() as session:
            for key, drive_def in fundamental_defs.items():
                drive_cfg = self.fundamental_config.get(key, {})
                is_enabled = drive_cfg.get("enabled", False)
                decay_cfg = drive_cfg.get("decay", {})
                rate = decay_cfg.get("rate", 10.0)
                interval = decay_cfg.get("interval_sec", 900)

                res = await session.execute(
                    select(DriveTable).where(DriveTable.name == drive_def["name"])
                )
                existing_drive = res.scalar_one_or_none()

                if is_enabled and not existing_drive:
                    # Драйв включен, но его нет -> создаем
                    new_drive = DriveTable(
                        id=str(uuid.uuid4())[:8],
                        name=drive_def["name"],
                        type="fundamental",
                        description=drive_def["description"],
                        decay_rate=rate,
                        decay_interval_sec=interval,
                        last_satisfied_at=datetime.now(timezone.utc),
                        recent_reflections=[],
                    )
                    session.add(new_drive)

                elif is_enabled and existing_drive:
                    # Динамически обновляем настройки, если пользователь изменил их в YAML
                    existing_drive.decay_rate = rate
                    existing_drive.decay_interval_sec = interval

                elif not is_enabled and existing_drive:
                    # Драйв выключен, но есть в БД -> удаляем
                    await session.delete(existing_drive)

            await session.commit()

    @skill()
    async def satisfy_drive(
        self, drive_name: str, amount: int, reflection_summary: str
    ) -> SkillResult:
        """
        Reduces drive deficit.

        Recommended iterative satisfaction:
        1-9% (superficial),
        10-15% (meaningful),
        16-25% (major achievements).
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

            # Защита от legacy/кривых данных: decay_rate обязан быть > 0, иначе математика
            # ниже рассыпается: current_deficit выйдет отрицательным или получим ZeroDivisionError.
            if drive.decay_rate <= 0 or drive.decay_interval_sec <= 0:
                return SkillResult.fail(
                    f"Драйв '{drive.name}' имеет невалидные настройки (rate={drive.decay_rate}, interval={drive.decay_interval_sec}). "
                    f"Ожидаются положительные числа."
                )

            # Высчитываем текущий дефицит через нелинейную модель
            current_deficit = self._calculate_deficit(
                last_sat, now, drive.decay_rate, drive.decay_interval_sec
            )

            # Считаем новый дефицит после удовлетворения
            new_deficit = max(0.0, current_deficit - amount)

            # Высчитываем время, когда дефицит был бы равен new_deficit
            intervals_ago = self._calculate_intervals_for_deficit(
                new_deficit, drive.decay_rate
            )
            drive.last_satisfied_at = now - timedelta(
                seconds=intervals_ago * drive.decay_interval_sec
            )

            time_str = format_datetime(now, self.tz_offset, "%m-%d %H:%M")
            entry = f"[{time_str}] Снижен на {amount}%: {reflection_summary}"

            current_refs = list(drive.recent_reflections)
            current_refs.insert(0, entry)
            drive.recent_reflections = current_refs[: self.max_history]

            await session.commit()

        main_logger.debug(f"[SQL DB] Дефицит драйва '{drive.name}' снижен на {amount}%.")
        return SkillResult.ok("True")

    @skill()
    async def create_custom_drive(
        self,
        name: str,
        description: str,
        decay_rate: float = 10.0,
        decay_interval_sec: int = 900,
    ) -> SkillResult:
        """
        Creates custom drive/motivator.
        """

        # Валидация
        if decay_rate <= 0 or decay_interval_sec <= 0:
            return SkillResult.fail(
                f"decay_rate и decay_interval_sec должны быть положительными числами. "
                f"Получено: rate={decay_rate}, interval={decay_interval_sec}."
            )

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
                decay_interval_sec=decay_interval_sec,
                last_satisfied_at=datetime.now(timezone.utc),
                recent_reflections=[],
            )
            session.add(new_drive)
            await session.commit()

        main_logger.debug(f"[SQL DB] Создан кастомный драйв '{name}'.")
        return SkillResult.ok("True")

    @skill()
    async def delete_custom_drive(self, drive_name: str) -> SkillResult:
        """
        Deletes custom drive.
        """

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

        main_logger.debug(f"[SQL DB] Удален кастомный драйв '{drive_name}'.")
        return SkillResult.ok("True")

    def _get_drive_semantic_state(self, name: str, deficit: int, description: str) -> str:
        """
        Переводит сухие проценты дефицита в утилитарное психологическое состояние.
        Нужно, чтобы агент видел конкретные директивы (Вектор действий и Тон).
        """

        # Определяем индекс ступени (1-5) по 20% на каждый шаг
        if deficit <= 20:
            step = 1
        elif deficit <= 40:
            step = 2
        elif deficit <= 60:
            step = 3
        elif deficit <= 80:
            step = 4
        else:
            step = 5

        # Выбираем текст из импортированной матрицы
        if name in DRIVES_SEMANTIC_MATRIX:
            state_text = DRIVES_SEMANTIC_MATRIX[name][step].strip()
        else:
            # Для кастомных драйвов подставляем их описание прямо в шаблон
            template = DRIVES_SEMANTIC_MATRIX["Custom"][step].strip()
            state_text = template.format(description=description)

        return f"\n{state_text}"

    async def get_context_block(self, **kwargs: Any) -> str:
        """Формирует Markdown-блок с семантическим самоощущением для системного промпта."""

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

        if not drives:
            return ""

        lines = [
            "## INTERNAL PSYCHOLOGICAL STATE",
            "Internal self-perceptions of the system, formed on the basis of a deficit of internal metrics:\n",
        ]

        now = datetime.now(timezone.utc)

        for d in drives:
            last_sat = (
                d.last_satisfied_at.replace(tzinfo=timezone.utc)
                if d.last_satisfied_at.tzinfo is None
                else d.last_satisfied_at
            )

            deficit = self._calculate_deficit(
                last_sat, now, d.decay_rate, d.decay_interval_sec
            )
            deficit_int = int(deficit)

            semantic_state = self._get_drive_semantic_state(d.name, deficit_int, d.description)

            # Выводим драйв в формате: * [CURIOSITY]: Текст состояния. (Deficit: X%)
            lines.append(f"* [{d.name}; Deficit: {deficit_int}%]: \n{semantic_state}")

            # Оставляем историю рефлексий, чтобы LLM понимала, что она делала недавно для закрытия этой потребности
            if d.recent_reflections:
                lines.append("  * Recent deficit reductions:*")
                for ref in d.recent_reflections[
                    :2
                ]:  # Берем только 2 последних, чтобы не спамить
                    limit = 200
                    short_ref = ref if len(ref) <= limit else ref[:limit] + "... [Обрезано]"
                    lines.append(f"    - {short_ref}")
            lines.append("")  # Пустая строка

        return "\n".join(lines).strip()

    # =======================================================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # =======================================================================================

    def _calculate_deficit(
        self, last_sat: datetime, now: datetime, decay_rate: float, decay_interval_sec: int
    ) -> float:
        """
        Прямая математика: вычисляет текущий процент дефицита от прошедшего времени.
        """

        intervals = (now - last_sat).total_seconds() / max(1, decay_interval_sec)

        if not self.dynamic_reduction:
            return min(100.0, intervals * decay_rate)

        # Вычисляем время (в интервалах) для прохождения каждой ступени
        t50 = 50.0 / decay_rate
        t80 = t50 + 30.0 / (decay_rate * 0.5)

        if intervals <= t50:
            deficit = intervals * decay_rate
        elif intervals <= t80:
            deficit = 50.0 + (intervals - t50) * (decay_rate * 0.5)
        else:
            deficit = 80.0 + (intervals - t80) * (decay_rate * 0.2)

        return min(100.0, deficit)

    def _calculate_intervals_for_deficit(self, deficit: float, decay_rate: float) -> float:
        """
        Обратная математика: переводит процент дефицита обратно в потраченные интервалы.
        """

        if not self.dynamic_reduction:
            return deficit / decay_rate

        t50 = 50.0 / decay_rate
        t80 = t50 + 30.0 / (decay_rate * 0.5)

        if deficit <= 50.0:
            return deficit / decay_rate
        elif deficit <= 80.0:
            return t50 + (deficit - 50.0) / (decay_rate * 0.5)
        else:
            return t80 + (deficit - 80.0) / (decay_rate * 0.2)

    async def adjust_downtime(self) -> None:
        """
        Компенсирует время, пока агент был выключен (даунтайм),
        сдвигая last_satisfied_at у всех драйвов.
        Это предотвращает мгновенный рост дефицита при долгом оффлайне.
        """
        if not self.pause_on_offline:
            return

        async with self.db.session_factory() as session:
            # Находим время последнего тика (сохраненного перед выключением)
            res = await session.execute(
                select(TickTable.created_at).order_by(desc(TickTable.created_at)).limit(1)
            )
            last_tick_time = res.scalar_one_or_none()

            if not last_tick_time:
                return

            now = datetime.now(timezone.utc)
            last_tick_time = (
                last_tick_time.replace(tzinfo=timezone.utc)
                if last_tick_time.tzinfo is None
                else last_tick_time
            )

            downtime = now - last_tick_time

            # Если даунтайм больше 1 минуты, компенсируем
            if downtime.total_seconds() > 60:
                drives_res = await session.execute(select(DriveTable))
                drives = drives_res.scalars().all()

                adjusted = 0
                for d in drives:
                    sat_time = (
                        d.last_satisfied_at.replace(tzinfo=timezone.utc)
                        if d.last_satisfied_at.tzinfo is None
                        else d.last_satisfied_at
                    )

                    # Игнорируем только те драйвы, которые были изменены строго после остановки системы
                    if sat_time > last_tick_time:
                        continue

                    d.last_satisfied_at = sat_time + downtime
                    adjusted += 1

                if adjusted > 0:
                    await session.commit()
                    main_logger.info(
                        f"[SQL DB] Даунтайм ({int(downtime.total_seconds())} сек) компенсирован для {adjusted} мотиваторов."
                    )
