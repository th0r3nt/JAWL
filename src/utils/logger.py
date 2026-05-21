"""
Central Logging Subsystem of the JAWL Framework.

Provides structured logging to physical files with automatic rotation and
ColorFormatter console outputs that dynamically style logs based on event severity,
and system components prefixes.
"""

import copy
import logging
import sys
from typing import List
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Registry of all created file handlers for dynamic configuration updates
_file_handlers_registry: List[RotatingFileHandler] = []


class LogColors:
    """ANSI color constants for terminal output."""

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
    Thread-safe log formatter without side-effects.
    Applies ANSI colors to terminal logs based on severity levels
    or unique message prefixes, respecting length constraints.
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
        # Create a shallow copy of the record to avoid mutating the original object
        # and disrupting file logging on other handlers
        rec = copy.copy(record)

        # Safely retrieve the raw message string
        msg_str = rec.getMessage()

        # Perform truncation for the console only on the isolated copy
        if len(msg_str) > self.max_console_length:
            truncated_msg = (
                msg_str[: self.max_console_length]
                + f"\n{LogColors.GRAY}...[Output truncated for terminal]{LogColors.RESET}"
            )
            rec.msg = truncated_msg
            rec.args = ()  # Clear args since the message is already formatted

        # Format the log line using standard mechanisms
        log_message = super().format(rec)

        # Determine color based on log level or prefix search
        color = ""
        if rec.levelno in self.LEVEL_COLORS:
            color = self.LEVEL_COLORS[rec.levelno]
        else:
            # Linear scan over the prefixes dictionary
            for prefix, prefix_color in self.PREFIX_COLORS.items():
                if prefix in msg_str:
                    color = prefix_color
                    break

        # Wrap in ANSI codes if a color was identified
        if color:
            return f"{color}{log_message}{LogColors.RESET}"

        return log_message


def setup_subsystem_logger(name: str, log_file: str, propagate: bool = True) -> logging.Logger:
    """
    Initializes a logger for a system component.

    Args:
        name: Unique logger name (e.g., 'JAWL.Agent').
        log_file: Target file name in the logs/ directory.
        propagate: If True, forwards entries to the parent logger (JAWL -> main.log).
    """

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    if "pytest" in sys.modules:
        log_file = "pytest.log"

    full_path = log_dir / log_file
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = propagate

    # File format (always verbose)
    file_fmt = "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Rotating file handler
    handler = RotatingFileHandler(
        full_path, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(fmt=file_fmt, datefmt=date_fmt))

    logger.addHandler(handler)
    _file_handlers_registry.append(handler)

    return logger


# 1. Root logger of the entire system (main.log)
main_logger = setup_subsystem_logger("JAWL", "main.log", propagate=False)

# Add stdout console stream handler to the root logger only
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    ColorFormatter(
        fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
)
main_logger.addHandler(console_handler)

# 2. Isolated subsystem loggers
# They write to their respective files AND propagate up to JAWL (main.log)
agent_logger = setup_subsystem_logger("JAWL.Agent", "agent.log")
swarm_logger = setup_subsystem_logger("JAWL.Swarm", "subagents.log")
tot_logger = setup_subsystem_logger("JAWL.ToT", "tot.log")
subc_logger = setup_subsystem_logger("JAWL.Subc", "subconscious.log")


def apply_logger_config(max_size_mb: float, backup_count: int) -> None:
    """Updates file rotation limits for all registered handlers."""
    max_bytes = int(max_size_mb * 1024 * 1024)
    for handler in _file_handlers_registry:
        handler.maxBytes = max_bytes
        handler.backupCount = backup_count


def update_log_level(level_str: str) -> None:
    """Updates the logging verbosity level for the JAWL hierarchy."""
    lvl = getattr(logging, level_str.upper(), logging.INFO)
    logging.getLogger("JAWL").setLevel(lvl)
