"""
Agent skills for manipulating own schedule (Calendar).

Allows the agent to set one-time alarms, interval checks,
or regular background tasks, providing a mechanism for deferred proactivity.
"""

import uuid
import time
from datetime import datetime, timedelta

from src.utils.logger import main_logger
from src.utils.dtime import get_timezone, format_timestamp

from src.l2_interfaces.calendar.client import CalendarClient
from src.l3_agent.skills.registry import skill, SkillResult


class CalendarManagement:
    """Local calendar management skills (alarms and timers)."""

    def __init__(self, client: CalendarClient) -> None:
        self.client = client
        self.tz = get_timezone(self.client.timezone)

    @skill()
    async def add_one_time_alarm(self, title: str, datetime_str: str) -> SkillResult:
        """
        Creates one-time alarm.

        datetime_str: Format 'YYYY-MM-DD HH:MM'.
        """
        try:
            # Parse the string considering system timezone
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
            trigger_at = dt.timestamp()

            if trigger_at <= time.time():
                return SkillResult.fail("Error: Specified time is already in the past.")

            ev_id = str(uuid.uuid4())
            self.client.add_event(
                {"id": ev_id, "title": title, "type": "one_time", "trigger_at": trigger_at}
            )

            main_logger.info(f"[Calendar] Added one-time timer '{title}' for {datetime_str}")
            return SkillResult.ok(f"True. ID: {ev_id[:8]}")

        except ValueError:
            return SkillResult.fail("Error: Invalid date format. Use 'YYYY-MM-DD HH:MM'.")
        except Exception as e:
            return SkillResult.fail(f"Error creating alarm: {e}")

    @skill()
    async def add_interval_alarm(self, title: str, interval_minutes: int) -> SkillResult:
        """
        Creates recurring timer triggering every N minutes from now.

        interval_minutes: Interval (e.g., 2880 = 2 days).
        """
        if interval_minutes < 1:
            return SkillResult.fail("Error: Interval must be at least 1 minute.")

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

            main_logger.info(
                f"[Calendar] Added interval timer '{title}' (every {interval_minutes} min)"
            )
            return SkillResult.ok(f"True. ID: {ev_id[:8]}")

        except Exception as e:
            return SkillResult.fail(f"Error creating timer: {e}")

    @skill()
    async def add_recurring_alarm(
        self, title: str, time_str: str, interval_days: int = 1
    ) -> SkillResult:
        """
        Creates recurring daily/weekly alarm.

        time_str: Format 'HH:MM'.
        interval_days: Step in days (1 = daily, 7 = weekly).
        """

        if interval_days < 1:
            return SkillResult.fail("Error: interval_days must be >= 1.")

        try:
            now_dt = datetime.now(self.tz)
            target_time = datetime.strptime(time_str, "%H:%M").time()

            # Combine trigger date for today
            target_dt = datetime.combine(now_dt.date(), target_time, tzinfo=self.tz)

            # If this time has already passed today, shift forward by the first interval
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

            main_logger.info(
                f"[Calendar] Added recurring timer '{title}' (at {time_str}, every {interval_days} days)"
            )
            return SkillResult.ok(f"True. ID: {ev_id[:8]}")

        except ValueError:
            return SkillResult.fail("Error: Invalid time format. Use 'HH:MM'.")

        except Exception as e:
            return SkillResult.fail(f"Error creating recurring timer: {e}")

    @skill()
    async def get_alarms(self) -> SkillResult:
        """
        Returns list of all alarms/timers.
        """

        events = self.client.get_all_events()
        if not events:
            return SkillResult.ok("Alarms list is empty.")

        lines = []
        for ev in events:
            dt_str = format_timestamp(ev["trigger_at"], self.client.timezone)
            if ev["type"] == "interval":
                meta = f"Interval: {ev.get('interval_minutes')} min."
            elif ev["type"] == "recurring":
                meta = f"Every {ev.get('interval_days')} days at {ev.get('time_str')}"
            else:
                meta = "One-time"

            lines.append(
                f"- [ID: `{ev['id'][:8]}`] {ev['title']} | Trigger: {dt_str} | Type: {meta}"
            )

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def delete_alarm(self, alarm_id: str) -> SkillResult:
        """
        Deletes existing alarm/timer.
        """

        events = self.client.get_all_events()

        filtered = [ev for ev in events if not ev["id"].startswith(alarm_id)]

        if len(filtered) == len(events):
            return SkillResult.fail(f"Alarm with ID {alarm_id} not found.")

        self.client.update_events(filtered)
        main_logger.info(f"[Calendar] Deleted timer ID: {alarm_id}")
        return SkillResult.ok("True")
