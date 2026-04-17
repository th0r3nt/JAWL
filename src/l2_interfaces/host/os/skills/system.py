import time
import psutil
from datetime import datetime, timezone, timedelta
from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSSystem:
    """
    Навыки агента для получения телеметрии и состояния ОС (кроссплатформенно).
    Используется для самодиагностики и сбора системного контекста.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client
        # Инициализируем счетчик CPU, чтобы последующие вызовы возвращали адекватный %
        psutil.cpu_percent(interval=None)

    def _get_uptime_string(self) -> str:
        """Внутренний метод для подсчета времени работы системы в формате HH:MM:SS."""

        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Если аптайм больше суток, добавляем дни
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"{days} дней, {hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    async def get_telemetry(self) -> SkillResult:
        """Возвращает загрузку CPU, свободной RAM и аптайм системы."""

        try:
            # interval=None позволяет вернуть значение мгновенно (не блокируя event loop)
            cpu_usage = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()

            uptime = self._get_uptime_string()

            # Форматируем байты в гигабайты для удобочитаемости
            total_ram_gb = round(mem.total / (1024**3), 1)
            free_ram_gb = round(mem.available / (1024**3), 1)

            report = (
                f"Системная телеметрия ОС:\n"
                f"- Загрузка CPU: {cpu_usage}%\n"
                f"- Использование RAM: {mem.percent}% (Свободно: {free_ram_gb} GB / {total_ram_gb} GB)\n"
                f"- Uptime: {uptime}"
            )

            return SkillResult.ok(report)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении телеметрии: {e}")

    @skill()
    async def list_top_processes(self) -> SkillResult:
        """Показывает процессы, потребляющие больше всего оперативной памяти."""

        limit = self.host_os.config.top_processes_limit

        try:
            processes = []

            # Собираем данные без задержек
            for p in psutil.process_iter(["pid", "name", "memory_percent"]):
                try:
                    processes.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # Сортируем по проценту ОЗУ (по убыванию)
            processes = sorted(
                processes,
                key=lambda x: x["memory_percent"] if x["memory_percent"] else 0,
                reverse=True,
            )[:limit]

            if not processes:
                return SkillResult.ok("Список процессов пуст.")

            lines = ["Топ процессов по ОЗУ:"]
            for p in processes:
                mem_pct = round(p["memory_percent"] or 0, 1)
                lines.append(f"- PID: `{p['pid']}` | RAM: {mem_pct}% | Имя: {p['name']}")

            system_logger.info(f"Запрошен список топ-{limit} процессов.")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка процессов: {e}")

    async def get_uptime(self) -> SkillResult:
        """Возвращает время непрерывной работы хост-системы (аптайм)."""

        uptime_str = self._get_uptime_string()
        return SkillResult.ok(f"{uptime_str}")

    async def get_datetime(self) -> SkillResult:
        """Возвращает текущую дату и время на сервере."""
        tz = timezone(timedelta(hours=self.host_os.timezone))
        current_dt = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        return SkillResult.ok(f"{current_dt}")
