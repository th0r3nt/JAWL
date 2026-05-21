"""
Isolated execution environment for agent Python scripts in the sandbox.

IMPORTANT: this is NOT real isolation. This is a best-effort in-process barrier.
For serious isolation use an external process + seccomp / Docker /
WASM / VM. See README, "Security and Disclaimer" section,
for the full list of vectors that the barrier does NOT cover.

What is blocked:
  - Path Traversal via ``builtins.open``, ``io.open``, ``os.open``,
    ``_io.FileIO``, ``pathlib`` (via patched ``builtins.open`` +
    low-level hooks).
  - Shell escape via ``subprocess.*``, ``os.system``, ``os.popen``,
    ``os.fork``/``execv*``/``posix_spawn*``/``spawn*``.
  - Bypass of patches via ``importlib.reload`` of protected modules.
  - Direct call of libc/msvcrt via ``ctypes.CDLL``.
  - Killing the parent process via ``os.kill``.
  - Leak of secrets via ``os.environ`` (scrubbing by allowlist names +
    hint-substring list).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Read root paths from the PARENT environment.
FW_DIR_STR = os.environ.get("JAWL_FRAMEWORK_DIR")
SB_DIR_STR = os.environ.get("JAWL_SANDBOX_DIR")
TARGET_SCRIPT = os.environ.get("JAWL_TARGET_SCRIPT")

if not FW_DIR_STR or not SB_DIR_STR or not TARGET_SCRIPT:
    print("FATAL ERROR: JAWL Sandbox paths not set.")
    sys.exit(1)

FRAMEWORK_DIR = Path(FW_DIR_STR).resolve()
SANDBOX_DIR = Path(SB_DIR_STR).resolve()

# _sandbox_guard.py lies in src/utils/templates/ next to this file
# in the source tree. When execute_script copies sandbox_runner.py
# into tmp-directory, it does not copy guard separately. Therefore we search
# for guard by absolute path inside FRAMEWORK_DIR.
_GUARD_PATH = FRAMEWORK_DIR / "src" / "utils" / "templates" / "_sandbox_guard.py"

if not _GUARD_PATH.is_file():
    print(f"FATAL ERROR: Sandbox guard module not found at {_GUARD_PATH}")
    sys.exit(1)

# Lazy loading of the guard via importlib so as not to drag extra sys.path,
# which could then be changed by user code.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("_sandbox_guard", _GUARD_PATH)
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)

_guard.install(FRAMEWORK_DIR, SANDBOX_DIR)

# sys.path for the target script
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
exec(code, globals_dict)  # noqa: S102 - intentional, this is a sandbox-runner
