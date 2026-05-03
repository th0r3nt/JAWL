"""
Изолированная среда выполнения для Python-скриптов агента в песочнице.

ВАЖНО: это НЕ настоящая изоляция. Это best-effort in-process barrier.
Для серьёзной изоляции используйте отдельный процесс + seccomp / Docker /
WASM / VM. Смотрите README, раздел "Безопасность и Отказ от
ответственности", для полного списка векторов, которые барьер НЕ
покрывает.

Что блокируется:
  - Path Traversal через ``builtins.open``, ``io.open``, ``os.open``,
    ``_io.FileIO``, ``pathlib`` (через патченный ``builtins.open`` +
    низкоуровневые хуки).
  - Shell escape через ``subprocess.*``, ``os.system``, ``os.popen``,
    ``os.fork``/``execv*``/``posix_spawn*``/``spawn*``.
  - Обход патчей через ``importlib.reload`` защищённых модулей.
  - Прямой вызов libc/msvcrt через ``ctypes.CDLL``.
  - Убийство родительского процесса через ``os.kill``.
  - Утечка секретов через ``os.environ`` (скрабинг по allowlist имён +
    hint-substring списку).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Читаем корневые пути из окружения РОДИТЕЛЯ.
FW_DIR_STR = os.environ.get("JAWL_FRAMEWORK_DIR")
SB_DIR_STR = os.environ.get("JAWL_SANDBOX_DIR")
TARGET_SCRIPT = os.environ.get("JAWL_TARGET_SCRIPT")

if not FW_DIR_STR or not SB_DIR_STR or not TARGET_SCRIPT:
    print("FATAL ERROR: JAWL Sandbox paths not set.")
    sys.exit(1)

FRAMEWORK_DIR = Path(FW_DIR_STR).resolve()
SANDBOX_DIR = Path(SB_DIR_STR).resolve()

# _sandbox_guard.py лежит в src/utils/templates/ рядом с этим файлом
# в исходном дереве. Когда execute_script копирует sandbox_runner.py
# в tmp-директорию, он не копирует guard отдельно. Поэтому ищем guard
# по абсолютному пути внутри FRAMEWORK_DIR.
_GUARD_PATH = FRAMEWORK_DIR / "src" / "utils" / "templates" / "_sandbox_guard.py"

if not _GUARD_PATH.is_file():
    print(f"FATAL ERROR: Sandbox guard module not found at {_GUARD_PATH}")
    sys.exit(1)

# Ленивая загрузка guard-а через importlib, чтобы не тащить лишний sys.path,
# который потом может поменять пользовательский код.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("_sandbox_guard", _GUARD_PATH)
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)

_guard.install(FRAMEWORK_DIR, SANDBOX_DIR)

# sys.path для целевого скрипта
sys.path.insert(0, str(Path(TARGET_SCRIPT).parent))
sys.path.insert(0, str(SANDBOX_DIR))

import builtins  # noqa: E402

with builtins.open(TARGET_SCRIPT, "r", encoding="utf-8") as f:
    code = f.read()

globals_dict = {
    "__name__": "__main__",
    "__file__": TARGET_SCRIPT,
    "__builtins__": builtins,
}
exec(code, globals_dict)  # noqa: S102 — интенционально, это sandbox-runner
