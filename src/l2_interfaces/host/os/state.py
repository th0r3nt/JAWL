
class HostOSState:
    """
    Хранит состояние Host OS.
    Телеметрия, время, аптайм.
    Обновляется слушателями (os/events.py) в фоне.
    """

    def __init__(self) -> None:
        self.is_online = False

        # Статические данные (определяются 1 раз при старте)
        self.os_info = "Неизвестно."  # Окно/Linux/Mac
        self.cpu_name = "Неизвестно."
        self.total_ram_gb = 0.0

        # Динамические данные
        self.datetime = "Неизвестно."  # Время
        self.uptime = "Неизвестно."  # Аптайм хост-пк
        self.telemetry = "Нет доступной телеметрии."  # CPU, ОЗУ, процессы
        self.sandbox_files = "Неизвестно."  # Текущие файлы в Sandbox
        self.framework_files = "Неизвестно."  # Дерево директории JAWL
        self.active_daemons = "Нет запущенных демонов."

        self.polling_interval = "Неизвестно."

        self.opened_workspace_files: set[str] = set()  # Файлы, открытые в "редакторе" агента
        self.recent_file_changes: list[str] = []  # Кэш последних diff-ов