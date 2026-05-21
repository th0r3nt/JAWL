"""
Wrapper that is executed when the agent wants to call a function from a sandbox/ file (RPC).
Contains built-in Sandbox Guard to protect the core from intrusion.

IMPORTANT: see _sandbox_guard.py - this is a best-effort in-process barrier,
not real isolation.
"""

import sys
import json
import asyncio
import traceback
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import inspect
import importlib.util

target_filepath = Path(sys.argv[1]).resolve()
func_name = sys.argv[2]
sandbox_dir = Path(sys.argv[3]).resolve()
framework_dir = sandbox_dir.parent

# Connect the shared Sandbox Guard (sets all protections: I/O, subprocess, fork,
# ctypes, importlib.reload, secret scrubbing in env, etc.).
# rpc_wrapper is copied to sandbox/_system/.tmp/ on launch, so look for
# _sandbox_guard.py by absolute path inside framework_dir.
_guard_path = framework_dir / "src" / "utils" / "templates" / "_sandbox_guard.py"

if not _guard_path.is_file():
    sys.stdout.write("\n---RPC_RESULT---\n")
    sys.stdout.write(
        json.dumps(
            {
                "status": "error",
                "error": f"Sandbox guard module not found at {_guard_path}",
            }
        )
        + "\n"
    )
    sys.exit(1)

_spec = importlib.util.spec_from_file_location("_sandbox_guard", _guard_path)
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
_guard.install(framework_dir, sandbox_dir)

# Guarantee paths are in sys.path for direct availability
script_dir = str(target_filepath.parent)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
if str(sandbox_dir) not in sys.path:
    sys.path.insert(0, str(sandbox_dir))

# Smart module name calculation to support relative imports inside packages
try:
    rel_path = target_filepath.relative_to(sandbox_dir)
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
            raise ImportError(f"Could not load module {target_filepath.name}")

        module = module_from_spec(spec)
        sys.modules[module_name] = module

        if "." in module_name:
            module.__package__ = module_name.rsplit(".", 1)[0]
        else:
            module.__package__ = ""

        spec.loader.exec_module(module)

        # INSTANTIATION AND METHOD CALL LOGIC
        if "." in func_name:
            class_name, method_name = func_name.split(".", 1)
            if not hasattr(module, class_name):
                raise AttributeError(
                    f"Object '{class_name}' not found in module {target_filepath.name}"
                )

            cls_obj = getattr(module, class_name)
            if inspect.isclass(cls_obj):
                instance = cls_obj()
                if not hasattr(instance, method_name):
                    raise AttributeError(f"Class '{class_name}' has no method '{method_name}'")
                func = getattr(instance, method_name)
            else:
                obj = getattr(module, class_name)
                func = getattr(obj, method_name)
        else:
            if not hasattr(module, func_name):
                raise AttributeError(
                    f"Module {target_filepath.name} has no function '{func_name}'"
                )
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
