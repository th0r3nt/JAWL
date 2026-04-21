import uuid
import time
from datetime import datetime, timedelta

from src.utils.logger import system_logger
from src.utils.dtime import get_timezone, format_timestamp

from src.l2_interfaces.calendar.client import CalendarClient
from src.l3_agent.skills.registry import skill, SkillResult


class CalendarManagement:
    """Навыки управления локальным календарем (будильники и таймеры)."""

    def __init__(self, client: CalendarClient):
        self.client = client
        self.tz = get_timezone(self.client.timezone)

    @skill()
    async def add_one_time_alarm(self, title: str, datetime_str: str) -> SkillResult:
        """
        Создает разовый будильник.
        datetime_str должен быть в формате 'YYYY-MM-DD HH:MM' (например, '2024-05-15 15:30').
        """

        try:
            # Парсим строку с учетом часового пояса системы
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
            trigger_at = dt.timestamp()

            if trigger_at <= time.time():
                return SkillResult.fail("Ошибка: Указанное время уже в прошлом.")

            ev_id = str(uuid.uuid4())
            self.client.add_event(
                {"id": ev_id, "title": title, "type": "one_time", "trigger_at": trigger_at}
            )

            system_logger.info(
                f"[Calendar] Добавлен разовый таймер '{title}' на {datetime_str}"
            )
            return SkillResult.ok(f"Разовый будильник успешно установлен (ID: {ev_id[:8]}).")

        except ValueError:
            return SkillResult.fail(
                "Ошибка: Неверный формат даты. Используйте 'YYYY-MM-DD HH:MM'."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании будильника: {e}")

    @skill()
    async def add_interval_alarm(self, title: str, interval_minutes: int) -> SkillResult:
        """
        Создает регулярный таймер, который будет срабатывать каждые N минут начиная от текущего момента.
        Например: 2880 мин. = каждые два дня.
        """

        # TODO: удобно?

        if interval_minutes < 1:
            return SkillResult.fail("Ошибка: Интервал должен быть не менее 1 минуты.")

        try:
            ev_id = str(uuid.uuid4())
            trigger_at = time.time() + (interval_minutes * 60)

            self.client.add_event(
                {
                    "id": ev_id,
                    "title": title,
                    "type": "interval",
                    "trigger_at": trigger_at,
                    "interval_minutes": interval_minutes,
                }
            )

            system_logger.info(
                f"[Calendar] Добавлен интервальный таймер '{title}' (каждые {interval_minutes} мин)"
            )
            return SkillResult.ok(f"Интервальный таймер успешно установлен (ID: {ev_id[:8]}).")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании таймера: {e}")

    @skill()
    async def add_recurring_alarm(
        self, title: str, time_str: str, interval_days: int = 1
    ) -> SkillResult:
        """
        Создает повторяющийся будильник на конкретное время дня.
        time_str: формат 'HH:MM' (например '09:00').
        interval_days: раз в сколько дней повторять (1 = каждый день, 7 = раз в неделю).
        """

        # TODO: даже я путаюсь в этой логике повторения, надо упростить для агента

        if interval_days < 1:
            return SkillResult.fail("Ошибка: interval_days должен быть >= 1.")

        try:
            now_dt = datetime.now(self.tz)
            target_time = datetime.strptime(time_str, "%H:%M").time()

            # Собираем дату срабатывания на сегодня
            target_dt = datetime.combine(now_dt.date(), target_time, tzinfo=self.tz)

            # Если это время сегодня уже прошло, переносим на первый интервал вперед
            if target_dt <= now_dt:
                target_dt += timedelta(days=interval_days)

            trigger_at = target_dt.timestamp()
            ev_id = str(uuid.uuid4())

            self.client.add_event(
                {
                    "id": ev_id,
                    "title": title,
                    "type": "recurring",
                    "trigger_at": trigger_at,
                    "time_str": time_str,
                    "interval_days": interval_days,
                }
            )

            system_logger.info(
                f"[Calendar] Добавлен повторяющийся таймер '{title}' (в {time_str}, каждые {interval_days} дн.)"
            )
            return SkillResult.ok(
                f"Повторяющийся таймер успешно установлен (ID: {ev_id[:8]})."
            )

        except ValueError:
            return SkillResult.fail("Ошибка: Неверный формат времени. Используйте 'HH:MM'.")
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании повторяющегося таймера: {e}")

    @skill()
    async def get_alarms(self) -> SkillResult:
        """Возвращает список всех существующих будильников и таймеров."""

        events = self.client.get_all_events()
        if not events:
            return SkillResult.ok("Список будильников пуст.")

        lines = []
        for ev in events:
            dt_str = format_timestamp(ev["trigger_at"], self.client.timezone)
            if ev["type"] == "interval":
                meta = f"Интервал: {ev.get('interval_minutes')} мин."

            elif ev["type"] == "recurring":
                meta = f"Каждые {ev.get('interval_days')} дн. в {ev.get('time_str')}"

            else:
                meta = "Разовый"

            lines.append(
                f"- [ID: `{ev['id'][:8]}`] {ev['title']} | Сработает: {dt_str} | Тип: {meta}"
            )

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def delete_alarm(self, alarm_id: str) -> SkillResult:
        """Удаляет существующий будильник или таймер по его ID."""
        
        events = self.client.get_all_events()

        filtered = [ev for ev in events if not ev["id"].startswith(alarm_id)]

        if len(filtered) == len(events):
            return SkillResult.fail(f"Будильник с ID {alarm_id} не найден.")

        self.client.update_events(filtered)
        system_logger.info(f"[Calendar] Удален таймер ID: {alarm_id}")
        return SkillResult.ok(f"Будильник {alarm_id} успешно удален.")
