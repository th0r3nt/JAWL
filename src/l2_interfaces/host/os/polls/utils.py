"""
Unified garbage filter. Wipes cache, logs, hidden files, and virtual environments.
"""

from pathlib import Path


def is_ignored(path: Path) -> bool:
    """Unified garbage filter. Wipes cache, logs, hidden files, and virtual environments."""
    ignore_dirs = {
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".git",
        "logs",
        "vector",
        "graph",
        "sql",
        ".jawl_events",
        "browser_profile",
    }
    ignore_exts = {
        ".pyc",
        ".pyo",
        ".pyd",
        ".tmp",
        ".swp",
        ".log",
        ".db",
        ".sqlite",
        ".sqlite3",
        "-journal",
        "-wal",
    }

    if path.suffix in ignore_exts or path.name.endswith("~"):
        return True

    for part in path.parts:
        if part in ignore_dirs:
            return True
        # Ignore hidden folders/files, but leave .env in case it is needed in the sandbox
        if part.startswith(".") and part not in {".", ".env"}:
            return True

    return False
