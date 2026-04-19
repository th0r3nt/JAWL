import logging
from typing import Union
from pathlib import Path


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
    PREFIX_COLORS = {
        "[Heartbeat]": LogColors.BRIGHT_MAGENTA,
        "[ReAct]": LogColors.BRIGHT_CYAN,
        "[Thoughts]": LogColors.MAGENTA,
        "[Agent Action]": LogColors.BRIGHT_GREEN,
        "[Agent Action Result]": LogColors.GRAY,
        "[Skills]": LogColors.GRAY,
        "[LLM]": LogColors.BRIGHT_BLUE,
        "[Host OS]": LogColors.GREEN,
        "[Web]": LogColors.MAGENTA,
        "[Telegram Telethon]": LogColors.CYAN,
        "[Telegram Aiogram]": LogColors.BLUE,
        "[Meta]": LogColors.WHITE,
        "[SQL DB]": LogColors.YELLOW,
        "[Vector DB]": LogColors.YELLOW,
        "[EventBus]": LogColors.GRAY,
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
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    full_path = log_dir / log_file

    file_format = "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    file_handler = logging.FileHandler(full_path, encoding="utf-8", mode="a")
    file_formatter = logging.Formatter(fmt=file_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler()
    color_formatter = ColorFormatter(
        fmt=file_format, datefmt=date_format, max_console_length=800
    )
    console_handler.setFormatter(color_formatter)

    specific_logger = logging.getLogger(name)
    specific_logger.setLevel(level)

    # Защита от дублирования логов при перезагрузках
    if not specific_logger.handlers:
        specific_logger.addHandler(file_handler)
        specific_logger.addHandler(console_handler)

    specific_logger.propagate = False
    return specific_logger


# Создаем логгер с уровнем INFO по умолчанию
system_logger = setup_specific_logger(name="SYSTEM", log_file="system.log", level=logging.INFO)


def update_log_level(level_str: str) -> None:
    """Динамически обновляет уровень логирования (вызывается после загрузки конфига)"""
    numeric_level = getattr(logging, level_str.upper(), logging.INFO)
    system_logger.setLevel(numeric_level)
    for handler in system_logger.handlers:
        handler.setLevel(numeric_level)
