import copy
import logging
import sys
from typing import List
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Реестр всех созданных файловых хендлеров для динамического обновления конфига
_file_handlers_registry: List[RotatingFileHandler] = []


class LogColors:
    """Константы ANSI-цветов для терминала."""

    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_WHITE = "\033[97m"
    BRIGHT_YELLOW = "\033[93m"


class ColorFormatter(logging.Formatter):
    """
    Потокобезопасный форматтер логов без побочных эффектов.
    Применяет ANSI-раскраску для терминала на основе уровня важности
    или уникальных префиксов сообщений, сохраняя ограничения по длине.
    """
    
    LEVEL_COLORS = {
        logging.DEBUG: LogColors.GRAY,
        logging.WARNING: LogColors.YELLOW,
        logging.ERROR: LogColors.RED,
        logging.CRITICAL: LogColors.RED,
    }

    PREFIX_COLORS = {
        "[Heartbeat]": LogColors.BRIGHT_MAGENTA,
        "[ReAct]": LogColors.BRIGHT_CYAN,
        "[Thoughts]": LogColors.MAGENTA,
        "[Agent Action]": LogColors.BRIGHT_GREEN,
        "[Agent Action Result]": LogColors.GRAY,
        "[Swarm]": LogColors.BRIGHT_YELLOW,
        "[Subagent ReAct]": LogColors.YELLOW,
        "[LLM]": LogColors.BRIGHT_BLUE,
        "[Tree of Thoughts]": LogColors.CYAN,
        "[Subconscious]": LogColors.BRIGHT_MAGENTA,
        "[System]": LogColors.BRIGHT_WHITE,
    }

    def __init__(self, fmt: str = None, datefmt: str = None, max_console_length: int = 800):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.max_console_length = max_console_length

    def format(self, record: logging.LogRecord) -> str:
        # Создаем поверхностную копию записи, чтобы не мутировать исходный объект
        # и не ломать логирование в файлы у других хендлеров
        rec = copy.copy(record)
        
        # Безопасно извлекаем исходную строку сообщения
        msg_str = rec.getMessage()
        
        # Выполняем обрезку для консоли только на изолированной копии
        if len(msg_str) > self.max_console_length:
            truncated_msg = (
                msg_str[: self.max_console_length]
                + f"\n{LogColors.GRAY}...[Вывод обрезан для терминала]{LogColors.RESET}"
            )
            rec.msg = truncated_msg
            rec.args = ()  # Сбрасываем аргументы, так как сообщение уже отформатировано
        
        # Форматируем строку лога стандартными средствами
        log_message = super().format(rec)
        
        # Определяем цвет на основе уровня лога или поиска префиксов
        color = ""
        if rec.levelno in self.LEVEL_COLORS:
            color = self.LEVEL_COLORS[rec.levelno]
        else:
            # Честный проход по словарю префиксов без преждевременных выходов
            for prefix, prefix_color in self.PREFIX_COLORS.items():
                if prefix in msg_str:
                    color = prefix_color
                    break  # Нашли совпадение — выходим из цикла

        # Оборачиваем в ANSI-код, если цвет определен
        if color:
            return f"{color}{log_message}{LogColors.RESET}"
            
        return log_message


def setup_subsystem_logger(name: str, log_file: str, propagate: bool = True) -> logging.Logger:
    """
    Инициализирует логгер для подсистемы.

    Args:
        name: Уникальное имя логгера (напр. 'JAWL.Agent').
        log_file: Имя файла в директории logs/.
        propagate: Если True, дублирует записи в родительский логгер (JAWL -> main.log).
    """

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    if "pytest" in sys.modules:
        log_file = "pytest.log"

    full_path = log_dir / log_file
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = propagate

    # Формат для файлов (всегда подробный)
    file_fmt = "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Файловый хендлер
    handler = RotatingFileHandler(
        full_path, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(fmt=file_fmt, datefmt=date_fmt))

    logger.addHandler(handler)
    _file_handlers_registry.append(handler)

    return logger


# 1. Корневой логгер всей системы (main.log)
main_logger = setup_subsystem_logger("JAWL", "main.log", propagate=False)

# Добавляем вывод в консоль только для корневого логгера
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    ColorFormatter(
        fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
)
main_logger.addHandler(console_handler)

# 2. Изолированные логгеры подсистем
# Они пишут в свои файлы И пробрасывают в JAWL (main.log)
agent_logger = setup_subsystem_logger("JAWL.Agent", "agent.log")
swarm_logger = setup_subsystem_logger("JAWL.Swarm", "subagents.log")
tot_logger = setup_subsystem_logger("JAWL.ToT", "tot.log")
subc_logger = setup_subsystem_logger("JAWL.Subc", "subconscious.log")


def apply_logger_config(max_size_mb: float, backup_count: int) -> None:
    """Обновляет настройки ротации для всех файлов логов."""
    max_bytes = int(max_size_mb * 1024 * 1024)
    for handler in _file_handlers_registry:
        handler.maxBytes = max_bytes
        handler.backupCount = backup_count


def update_log_level(level_str: str) -> None:
    """Обновляет уровень логирования для всей иерархии JAWL."""
    lvl = getattr(logging, level_str.upper(), logging.INFO)
    logging.getLogger("JAWL").setLevel(lvl)
