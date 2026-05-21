"""
Helper and Utility Tools for the JAWL Framework.

Provides common utility functions for file size formatting, secure sandbox path validation
(Gatekeeper), text truncation safeguards, HTML stripping, coordinate grid overlays,
and OS-level exclusive locking (Mutex).
"""

import os
import json
from pathlib import Path
from typing import Union, Optional, IO
import re
import html

from src.utils.logger import main_logger


def format_size(size_bytes: int) -> str:
    """
    Converts bytes into a human-readable size string.

    Args:
        size_bytes (int): File size in bytes.

    Returns:
        str: Human-readable size with appropriate unit.
    """

    if size_bytes < 0:
        return f"-{format_size(-size_bytes)}"

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(size_bytes)
    for unit in units[:-1]:
        if size < 1024:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


def validate_sandbox_path(filepath: str | Path) -> Path:
    """
    Sandbox path validator and Gatekeeper.
    Restricts file actions strictly within the designated sandbox/ directory,
    protecting the system from path traversal attempts.

    Args:
        filepath (str | Path): Relative or absolute path requested by the agent.

    Returns:
        Path: Resolved absolute physical path within the sandbox bounds.

    Raises:
        PermissionError: If the requested path escapes the sandbox directory.
    """

    sandbox_dir = (Path.cwd() / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    path_str = str(filepath).replace("\\", "/")
    if path_str.startswith("sandbox/"):
        path_str = path_str[8:]

    resolved = (sandbox_dir / path_str).resolve()
    if not resolved.is_relative_to(sandbox_dir):
        raise PermissionError(
            "Access denied: you can work with files strictly within the sandbox/ folder"
        )

    return resolved


def parse_int_or_str(value: Union[int, str]) -> Union[int, str]:
    """
    Safely converts string IDs to integers.
    If the value cannot be parsed to an int, returns the stripped raw string.

    Args:
        value (Union[int, str]): Raw ID value.

    Returns:
        Union[int, str]: Integer value or clean string username/identifier.
    """

    try:
        return int(value)
    except ValueError:
        return str(value).strip()


def truncate_text(
    text: str,
    max_chars: int,
    suffix: str = "\n... [Output truncated. Character limit exceeded]",
) -> str:
    """
    Safeguards the agent's context window by truncating extremely long texts.

    Args:
        text (str): Raw target text.
        max_chars (int): Maximum allowed characters ceiling limit.
        suffix (str, optional): Appended truncation notice string.

    Returns:
        str: Truncated or original text conforming strictly to max_chars limit.
    """

    if max_chars <= 0:
        return ""

    if len(text) <= max_chars:
        return text

    if len(suffix) >= max_chars:
        return suffix[:max_chars]

    body_budget = max_chars - len(suffix)
    return text[:body_budget] + suffix


def get_project_root() -> Path:
    """
    Resolves and returns the absolute path of the JAWL framework root directory.

    Returns:
        Path: Absolute path of the framework directory.
    """

    return Path(__file__).resolve().parent.parent.parent


def get_pid_file_path() -> Path:
    """
    Returns the unified physical path to the runtime PID file.

    Returns:
        Path: Path to the agent.pid file.
    """

    return get_project_root() / "src" / "utils" / "local" / "data" / "agent.pid"


def get_lock_file_path() -> Path:
    """
    Returns the unified physical path to the Mutex lock file.

    Returns:
        Path: Path to the agent.lock file.
    """

    return get_project_root() / "src" / "utils" / "local" / "data" / "agent.lock"


def clean_html(raw_html: str) -> str:
    """
    Strips raw HTML tags, inline CSS styles, JS blocks, and comments to save context tokens.

    Args:
        raw_html (str): Source HTML markup.

    Returns:
        str: Sanitized clean text.
    """

    if not raw_html:
        return ""

    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def draw_image_grid(image_path: str | Path, step: int = 100) -> None:
    """
    Draws a semi-transparent grid overlay with coordinate labels on an image.
    Used by take_screenshot for visual positioning in Multimodal Vision LLMs.

    Args:
        image_path (str | Path): Path to the target image.
        step (int): Grid line spacing step in pixels.
    """

    from PIL import Image, ImageDraw

    with Image.open(image_path) as img:
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        width, height = img.size

        for x in range(0, width, step):
            draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 80), width=1)
        for y in range(0, height, step):
            draw.line([(0, y), (width, y)], fill=(255, 0, 0, 80), width=1)

        for x in range(0, width, step):
            for y in range(0, height, step):
                text = f"{x},{y}"
                text_w = len(text) * 6
                text_w = min(text_w, width - x - 4)  # Clamp bounds protection
                text_h = 10

                draw.rectangle(
                    [x + 2, y + 2, x + 4 + text_w, y + 4 + text_h], fill=(255, 255, 255, 220)
                )
                draw.text((x + 4, y + 2), text, fill=(255, 0, 0, 255))

        combined = Image.alpha_composite(img.convert("RGBA"), overlay)
        combined.convert("RGB").save(image_path)


def dump_prompt_to_file(filename: str, messages: list, meta_header: str = "") -> None:
    """
    Dumps the compiled system prompt context to a Markdown file for debugging.

    Args:
        filename (str): Target output file path.
        messages (list): Array of API formatted message dicts.
        meta_header (str): Header text block.
    """
    try:
        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            if meta_header:
                f.write(f"{meta_header}\n\n---\n\n")

            for m in messages:
                role = getattr(
                    m, "role", m.get("role", "unknown") if isinstance(m, dict) else "unknown"
                )
                content = getattr(
                    m, "content", m.get("content", "") if isinstance(m, dict) else ""
                )
                f.write(f"### Role: {role}\n{content}\n\n---\n")
    except Exception as e:
        main_logger.error(f"[System] Failed to save prompt to {filename}: {e}")


def get_python_module_docstring(filepath: Path, max_length: int = 150) -> str:
    """
    Extracts the module-level docstring from a Python file.

    Args:
        filepath (Path): Target Python file.
        max_length (int): Characters output ceiling limit.

    Returns:
        str: Formatted module docstring or empty string.
    """
    if filepath.suffix.lower() != ".py":
        return ""

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            head = f.read(2048)

        match = re.search(r"^\s*(?:#.*?\n\s*)*(['\"]{3})(.*?)\1", head, re.DOTALL)

        if match:
            doc = match.group(2)
            clean_doc = " ".join(doc.split())

            if len(clean_doc) > max_length:
                clean_doc = clean_doc[:max_length] + "..."

            return f' ["""{clean_doc}"""]'

        return ""
    except Exception:
        return ""


class SystemInstanceLock:
    """
    Exclusive system instance process lock (Mutex) using a physical lock file.
    Cross-platform implementation utilizing msvcrt (Windows) and fcntl (Unix).
    """

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self._file: Optional[IO] = None

    def acquire(self) -> bool:
        """
        Attempts to acquire an exclusive lock.

        Returns:
            bool: True if the lock was successfully acquired, False otherwise.
        """
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file = open(self.lock_file, "a+", encoding="utf-8")
            fd = self._file.fileno()

            if os.name == "nt":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            self._file.seek(0)
            self._file.truncate()
            self._file.write(str(os.getpid()))
            self._file.flush()
            return True

        except (IOError, OSError, PermissionError):
            if self._file:
                self._file.close()
                self._file = None
            return False

    def release(self) -> None:
        """Saves current state and releases the acquired lock."""
        if self._file:
            try:
                fd = self._file.fileno()
                if os.name == "nt":
                    import msvcrt

                    self._file.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass

            try:
                self._file.close()
            except Exception:
                pass
            self._file = None


def is_agent_running() -> bool:
    """
    Verifies if an active instance of the agent is currently running.
    Utilizes OS file lock verification for precise results.

    Returns:
        bool: True if the agent is running, False otherwise.
    """
    lock_file = get_lock_file_path()
    pid_file = get_pid_file_path()

    if not lock_file.exists() or not pid_file.exists():
        try:
            pid_file.unlink(missing_ok=True)
            lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    is_locked = False
    try:
        with open(lock_file, "a+", encoding="utf-8") as f:
            fd = f.fileno()
            if os.name == "nt":
                import msvcrt

                f.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
    except (IOError, OSError, PermissionError) as e:
        if isinstance(e, FileNotFoundError):
            is_locked = False
        else:
            is_locked = True

    if is_locked:
        return True

    try:
        pid_file.unlink(missing_ok=True)
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass

    return False


def get_system_uptime_path() -> Path:
    """
    Returns the path to the system uptime file.

    Returns:
        Path: Path to system_uptime.json.
    """
    return get_project_root() / "src" / "utils" / "local" / "data" / "system_uptime.json"


def update_last_active_time() -> None:
    """
    Writes the current Unix timestamp to system_uptime.json.
    Used for tracking exact offline downtime.
    """
    import time

    try:
        path = get_system_uptime_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"last_active_at": time.time()}, f)
    except Exception as e:
        main_logger.debug(f"[System] Failed to write last active metadata: {e}")


def get_last_active_time() -> Optional[float]:
    """
    Reads the last saved active timestamp from system_uptime.json.

    Returns:
        Optional[float]: Unix timestamp or None if file doesn't exist.
    """
    try:
        path = get_system_uptime_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_active_at")
    except Exception:
        pass
    return None
