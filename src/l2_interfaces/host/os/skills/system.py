import time
import psutil

from src.utils.logger import system_logger
from src.utils.dtime import get_now_formatted, seconds_to_duration_str

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

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

    @skill()
    @require_access(HostOSAccessLevel.OBSERVER)
    async def get_telemetry(self) -> SkillResult:
        """
        Возвращает загрузку CPU, свободной RAM и аптайм системы.
        """

        try:
            cpu_usage = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()

            uptime = seconds_to_duration_str(time.time() - psutil.boot_time())

            total_ram_gb = self.host_os.state.total_ram_gb
            free_ram_gb = round(mem.available / (1024**3), 1)

            report = (
                f"- OS: {self.host_os.state.os_info}\n"
                f"- Модель CPU: {self.host_os.state.cpu_name}\n"
                f"- Загрузка CPU: {cpu_usage}%\n"
                f"- Использование RAM: {mem.percent}% (Свободно: {free_ram_gb} GB / {total_ram_gb} GB)\n"
                f"- Uptime: {uptime}"
            )

            return SkillResult.ok(report)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении телеметрии: {e}")

    @skill()
    @require_access(HostOSAccessLevel.OBSERVER)
    async def list_top_processes(self) -> SkillResult:
        """
        Показывает процессы, потребляющие больше всего оперативной памяти.
        """

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

            system_logger.info(f"[Host OS] Запрошен список топ-{limit} процессов.")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка процессов: {e}")

    @skill()
    @require_access(HostOSAccessLevel.OBSERVER)
    async def get_uptime(self) -> SkillResult:
        """
        Возвращает время непрерывной работы хост-системы.
        """
        uptime_str = seconds_to_duration_str(time.time() - psutil.boot_time())
        return SkillResult.ok(uptime_str)

    @skill()
    @require_access(HostOSAccessLevel.OBSERVER)
    async def get_datetime(self) -> SkillResult:
        """
        Возвращает текущую дату и время на сервере.
        """
        return SkillResult.ok(get_now_formatted(self.host_os.timezone))
