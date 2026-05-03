"""
Изолированная среда выполнения для Python-скриптов агента в песочнице.

ВАЖНО: это НЕ настоящая изоляция. Это best-effort in-process barrier.
Для серьёзной изоляции используйте отдельный процесс + seccomp / Docker /
WASM / VM. Смотрите документацию ``_sandbox_guard.py`` для списка
векторов, которые барьер НЕ покрывает.

Что блокируется:
  - Path Traversal через ``builtins.open``, ``io.open``, ``os.open``,
    ``_io.FileIO``, ``pathlib`` (через патченный ``builtins.open``).
  - Shell escape через ``subprocess.*``, ``os.system``, ``os.popen``,
    ``os.fork``/``execv*``/``posix_spawn*``/``spawn*``.
  - Обход патчей через ``importlib.reload`` protected-модулей.
  - Прямой вызов libc/msvcrt через ``ctypes.CDLL``.
  - Убийство родительского процесса через ``os.kill``.
  - Утечка секретов через ``os.environ`` (скрабинг по префиксам).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Читаем корневые пути из окружения РОДИТЕЛЯ до скрабинга.
FW_DIR_STR = os.environ.get("JAWL_FRAMEWORK_DIR")
SB_DIR_STR = os.environ.get("JAWL_SANDBOX_DIR")
TARGET_SCRIPT = os.environ.get("JAWL_TARGET_SCRIPT")

if not FW_DIR_STR or not SB_DIR_STR or not TARGET_SCRIPT:
    print("FATAL ERROR: JAWL Sandbox paths not set.")
    sys.exit(1)

FRAMEWORK_DIR = Path(FW_DIR_STR).resolve()
SANDBOX_DIR = Path(SB_DIR_STR).resolve()

# _sandbox_guard.py должен лежать рядом; добавляем его директорию в sys.path
# до инициализации, чтобы импорт гарантированно сработал вне зависимости от
# того, как был запущен интерпретатор.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sandbox_guard import install as _install_sandbox  # noqa: E402

# Устанавливаем все защиты ДО запуска целевого скрипта.
_install_sandbox(FRAMEWORK_DIR, SANDBOX_DIR)

# sys.path для целевого скрипта
sys.path.insert(0, str(Path(TARGET_SCRIPT).parent))
sys.path.insert(0, str(SANDBOX_DIR))

# Читаем код целевого скрипта через уже защищённый open — патч уже активен,
# но файл находится внутри sandbox/ и разрешён.
import builtins  # noqa: E402  (needs to happen after install)

with builtins.open(TARGET_SCRIPT, "r", encoding="utf-8") as f:
    code = f.read()

globals_dict = {
    "__name__": "__main__",
    "__file__": TARGET_SCRIPT,
    "__builtins__": builtins,
}
exec(code, globals_dict)  # noqa: S102 — интенционально, это sandbox-runner
