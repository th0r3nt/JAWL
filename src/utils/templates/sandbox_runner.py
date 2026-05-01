"""
Изолированная среда выполнения для Python-скриптов агента в песочнице.
Перехватывает попытки выхода за пределы sandbox/ (Path Traversal),
а также блокирует модули `os.system` и `subprocess`.
"""

import sys
import os
import builtins
from pathlib import Path
import subprocess

# Читаем корневые пути из окружения
FW_DIR_STR = os.environ.get("JAWL_FRAMEWORK_DIR")
SB_DIR_STR = os.environ.get("JAWL_SANDBOX_DIR")
TARGET_SCRIPT = os.environ.get("JAWL_TARGET_SCRIPT")

if not FW_DIR_STR or not SB_DIR_STR or not TARGET_SCRIPT:
    print("FATAL ERROR: JAWL Sandbox paths not set.")
    sys.exit(1)

FRAMEWORK_DIR = Path(FW_DIR_STR).resolve()
SANDBOX_DIR = Path(SB_DIR_STR).resolve()

# Патч функции builtins.open
_orig_open = builtins.open


def _safe_open(
    file,
    mode="r",
    buffering=-1,
    encoding=None,
    errors=None,
    newline=None,
    closefd=True,
    opener=None,
):
    try:
        # Пытаемся разрезолвить путь
        p = Path(file).resolve()

        # Разрешаем доступ к системным библиотекам Python (site-packages, lib)
        if "Python" in str(p) or "site-packages" in str(p) or "lib" in str(p).lower():
            pass
        # Если файл внутри директории фреймворка, но НЕ внутри песочницы - БЛОКИРУЕМ
        elif p.is_relative_to(FRAMEWORK_DIR) and not p.is_relative_to(SANDBOX_DIR):
            raise PermissionError(
                f"[Sandbox Guard] Access Denied: Path Traversal попытка заблокирована. Доступ к '{file}' запрещен."
            )
    except Exception as e:
        if isinstance(e, PermissionError):
            raise e
        # Если путь кривой и не резолвится, пускаем дальше, чтобы open сам упал с FileNotFoundError
        pass

    return _orig_open(file, mode, buffering, encoding, errors, newline, closefd, opener)


builtins.open = _safe_open


# Предотвращение Shell Escape
def _blocked_func(*args, **kwargs):
    raise PermissionError(
        "[Sandbox Guard] Access Denied: Использование shell/subprocess заблокировано в целях безопасности."
    )


subprocess.Popen = _blocked_func
subprocess.run = _blocked_func
subprocess.check_output = _blocked_func
subprocess.call = _blocked_func

os.system = _blocked_func
os.popen = _blocked_func

# Добавляем пути в sys.path для корректных импортов
sys.path.insert(0, str(Path(TARGET_SCRIPT).parent))
sys.path.insert(0, str(SANDBOX_DIR))

# Выполняем целевой скрипт
with _orig_open(TARGET_SCRIPT, "r", encoding="utf-8") as f:
    code = f.read()

# Эмулируем __main__ для правильного запуска if __name__ == '__main__':
globals_dict = {"__name__": "__main__", "__file__": TARGET_SCRIPT, "__builtins__": builtins}
exec(code, globals_dict)
