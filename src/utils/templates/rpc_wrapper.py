import sys
import json
import asyncio
import traceback
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

target_filepath = sys.argv[1]
func_name = sys.argv[2]
target_dir = str(Path(target_filepath).parent)
if target_dir not in sys.path:
    sys.path.insert(0, target_dir)

async def _runner(func, kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(**kwargs)
    return func(**kwargs)

def main():
    try:
        input_data = sys.stdin.read()
        kwargs = json.loads(input_data) if input_data.strip() else {}

        spec = spec_from_file_location("dynamic_sandbox_module", target_filepath)
        if spec is None or spec.loader is None:
            raise ImportError(f"Не удалось загрузить модуль {target_filepath}")
            
        module = module_from_spec(spec)
        sys.modules["dynamic_sandbox_module"] = module
        spec.loader.exec_module(module)

        if not hasattr(module, func_name):
            raise AttributeError(f"В модуле {target_filepath} нет функции '{func_name}'")

        func = getattr(module, func_name)
        result = asyncio.run(_runner(func, kwargs))
        
        sys.stdout.write("\n---RPC_RESULT---\n")
        sys.stdout.write(json.dumps({"status": "ok", "result": result}, ensure_ascii=False) + "\n")

    except BaseException as e:
        sys.stdout.write("\n---RPC_RESULT---\n")
        sys.stdout.write(json.dumps({
            "status": "error", 
            "error": f"{type(e).__name__}: {str(e)}", 
            "traceback": traceback.format_exc()
        }, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()