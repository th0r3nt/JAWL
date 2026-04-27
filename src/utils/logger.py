import logging
import sys
from typing import Union
from pathlib import Path
from logging.handlers import RotatingFileHandler


class LogColors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


class ColorFormatter(logging.Formatter):
    """
    Кастомный форматтер логов.
    Раскрашивает префиксы подсистем в терминале и обрезает слишком длинные сообщения,
    сохраняя при этом полный дамп для файлового вывода.
    """

    PREFIX_COLORS = {
        # Агент
        "[Heartbeat]": LogColors.BRIGHT_MAGENTA,
        "[ReAct]": LogColors.BRIGHT_CYAN,
        "[Thoughts]": LogColors.MAGENTA,
        "[Agent Action]": LogColors.BRIGHT_GREEN,
        "[Agent Action Result]": LogColors.GRAY,
        # Скиллы/интерфейсы
        "[Skills]": LogColors.GRAY,
        "[LLM]": LogColors.BRIGHT_BLUE,
        "[Host OS]": LogColors.GREEN,
        "[Web]": LogColors.MAGENTA,
        "[Telegram Telethon]": LogColors.CYAN,
        "[Telegram Aiogram]": LogColors.BLUE,
        "[Meta]": LogColors.WHITE,
        "[Multimodality]": LogColors.GREEN,
        "[Github]": LogColors.BLUE,
        "[Email]": LogColors.MAGENTA,
        "[Calendar]": LogColors.CYAN,
        # Базы данных
        "[SQL DB]": LogColors.YELLOW,
        "[Vector DB]": LogColors.YELLOW,
        "[EventBus]": LogColors.GRAY,
        # Общее
        "[System]": LogColors.BRIGHT_WHITE,
    }

    def __init__(self, fmt=None, datefmt=None, max_console_length=800):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.max_console_length = max_console_length

    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.msg
        try:
            msg_str = str(original_msg)
            if len(msg_str) > self.max_console_length:
                record.msg = (
                    msg_str[: self.max_console_length]
                    + f"\n{LogColors.GRAY}...[Вывод обрезан для терминала. Полный дамп сохранен в system.log]{LogColors.RESET}"
                )

            log_message = super().format(record)

            if record.levelno >= logging.ERROR:
                return f"{LogColors.BRIGHT_RED}{log_message}{LogColors.RESET}"
            if record.levelno == logging.WARNING:
                return f"{LogColors.BRIGHT_YELLOW}{log_message}{LogColors.RESET}"

            for prefix, color in self.PREFIX_COLORS.items():
                if prefix in msg_str:
                    return f"{color}{log_message}{LogColors.RESET}"

            return log_message

        finally:
            # Возвращаем оригинальное сообщение обратно в объект Record.
            # Благодаря этому FileHandler (который пишет в файл) сохранит строку целиком без ANSI-кодов и обрезки
            record.msg = original_msg


def setup_specific_logger(name: str, log_file: str, level: Union[int, str]) -> logging.Logger:
    """
    Инициализирует логгер с двойным выводом (терминал + файл).
    Защищает от дублирования хендлеров при перезагрузках системы.
    """

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    is_testing = "pytest" in sys.modules

    # Изолируем логи тестов в отдельный файл, чтобы подпроцесс деплоя не засорял system.log агента
    if is_testing:
        log_file = "pytest.log"

    full_path = log_dir / log_file

    file_format = "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # RotatingFileHandler - базовые 5 МБ, обновится позже из конфига
    file_handler = RotatingFileHandler(
        full_path, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
    )
    file_formatter = logging.Formatter(fmt=file_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler()
    color_formatter = ColorFormatter(
        fmt=file_format, datefmt=date_format, max_console_length=800
    )
    console_handler.setFormatter(color_formatter)

    if is_testing:
        console_handler.setLevel(logging.CRITICAL)

    specific_logger = logging.getLogger(name)
    specific_logger.setLevel(level)

    if not specific_logger.handlers:
        specific_logger.addHandler(file_handler)
        specific_logger.addHandler(console_handler)

    specific_logger.propagate = False
    return specific_logger


# Создаем логгер с уровнем INFO по умолчанию
system_logger = setup_specific_logger(name="SYSTEM", log_file="system.log", level=logging.INFO)


def apply_logger_config(max_size_mb: float, backup_count: int) -> None:
    """Динамически обновляет лимиты ротации логов из YAML конфигурации."""
    max_bytes = int(max_size_mb * 1024 * 1024)
    for handler in system_logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            handler.maxBytes = max_bytes
            handler.backupCount = backup_count


def update_log_level(level_str: str) -> None:
    """Динамически обновляет уровень логирования (вызывается после загрузки конфига)"""
    numeric_level = getattr(logging, level_str.upper(), logging.INFO)
    system_logger.setLevel(numeric_level)

    for handler in system_logger.handlers:
        # Защищаем нашу тишину в консоли от сброса во время тестов.
        # Используем type(handler) is logging.StreamHandler, т.к. RotatingFileHandler наследуется от StreamHandler,
        # и isinstance() случайно замьютил бы и файловый лог.
        if "pytest" in sys.modules and type(handler) is logging.StreamHandler:
            continue
        handler.setLevel(numeric_level)
