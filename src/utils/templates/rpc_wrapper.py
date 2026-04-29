"""
Обертка, которая выполняется, когда агент хочет вызвать функцию из sandbox/ файла.
"""

import sys
import json
import asyncio
import traceback
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

target_filepath = Path(sys.argv[1]).resolve()
func_name = sys.argv[2]
sandbox_dir = Path(sys.argv[3]).resolve()

# Гарантируем наличие путей в sys.path для прямой доступности
script_dir = str(target_filepath.parent)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
if str(sandbox_dir) not in sys.path:
    sys.path.insert(0, str(sandbox_dir))

# Умное вычисление имени модуля для поддержки относительных импортов внутри пакетов
try:
    rel_path = target_filepath.relative_to(sandbox_dir)
    # my_folder/my_script.py -> my_folder.my_script
    module_name = ".".join(rel_path.with_suffix("").parts)
except ValueError:
    module_name = "dynamic_sandbox_module"


async def _runner(func, kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(**kwargs)
    return func(**kwargs)


def main():
    try:
        input_data = sys.stdin.read()
        kwargs = json.loads(input_data) if input_data.strip() else {}

        spec = spec_from_file_location(module_name, str(target_filepath))
        if spec is None or spec.loader is None:
            raise ImportError(f"Не удалось загрузить модуль {target_filepath.name}")

        module = module_from_spec(spec)
        sys.modules[module_name] = module

        # Устанавливаем __package__, чтобы работали относительные импорты (from . import x)
        if "." in module_name:
            module.__package__ = module_name.rsplit(".", 1)[0]
        else:
            module.__package__ = ""

        spec.loader.exec_module(module)

        if not hasattr(module, func_name):
            raise AttributeError(f"В модуле {target_filepath.name} нет функции '{func_name}'")

        func = getattr(module, func_name)
        result = asyncio.run(_runner(func, kwargs))

        sys.stdout.write("\n---RPC_RESULT---\n")
        sys.stdout.write(
            json.dumps({"status": "ok", "result": result}, ensure_ascii=False) + "\n"
        )

    except BaseException as e:
        sys.stdout.write("\n---RPC_RESULT---\n")
        sys.stdout.write(
            json.dumps(
                {
                    "status": "error",
                    "error": f"{type(e).__name__}: {str(e)}",
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
