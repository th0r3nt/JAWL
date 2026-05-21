"""
Main launch script for the JAWL framework.
Acts as a smart bootstrapper: verifies the virtual environment,
installs dependencies, and runs the CLI interface.
"""

import os
import sys
import subprocess
import time
import venv
import shutil
from pathlib import Path
import json
import uuid

from src import __version__


def is_venv() -> bool:
    """Checks if the script is running inside a virtual environment."""
    return sys.prefix != sys.base_prefix


def recover_deploy_crashes(root_dir: Path):
    """
    Resurrection mechanism: rolls back broken code if the process died during deployment.
    """
    backup_dir = root_dir / "src" / "utils" / "local" / "data" / "deploy_backup"
    active_flag = backup_dir / ".deploy_active"

    if backup_dir.exists() and active_flag.exists():
        print("[*] Critical crash detected during deploy session.")
        print("[*] The agent broke the code. Initiating automatic rollback of source files.")

        try:
            for r, d, files in os.walk(backup_dir):
                if "__pycache__" in r:
                    continue
                for file in files:
                    if file in (".deploy_active", ".newfiles_manifest") or file.endswith(
                        ".pyc"
                    ):
                        continue
                    b_path = Path(r) / file
                    rel_path = b_path.relative_to(backup_dir)
                    target_path = root_dir / rel_path

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(b_path, target_path)

            manifest = backup_dir / ".newfiles_manifest"
            if manifest.exists():
                with open(manifest, "r", encoding="utf-8") as f:
                    new_files = f.read().splitlines()
                for nf in new_files:
                    if nf:
                        target = root_dir / nf
                        if target.exists():
                            if target.is_dir():
                                shutil.rmtree(target, ignore_errors=True)
                            else:
                                target.unlink(missing_ok=True)

            shutil.rmtree(backup_dir, ignore_errors=True)

            events_dir = root_dir / "sandbox" / ".jawl_events"
            events_dir.mkdir(parents=True, exist_ok=True)
            evt_id = str(uuid.uuid4())
            data = {
                "message": "Critical failure. The previous code (in the deploy session) caused a fatal crash. The bootstrapper automatically rolled back the source files. Please avoid seppuku.",
                "payload": {},
            }
            with open(
                events_dir / f"{int(time.time())}_{evt_id}.json", "w", encoding="utf-8"
            ) as f:
                json.dump(data, f, ensure_ascii=False)

            print("[*] Rollback completed successfully. Launching stable version.")
            time.sleep(2)

        except Exception as e:
            print(f"[!] Error during deploy rollback: {e}")


def setup_and_run() -> None:
    root_dir = Path(__file__).resolve().parent
    venv_dir = root_dir / "venv"
    req_file = root_dir / "requirements.txt"

    recover_deploy_crashes(root_dir)

    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env.pop("PYTHONHOME", None)

    # =========================================================
    # If we are OUTSIDE the virtual environment (Global Python)
    # =========================================================

    if not is_venv():
        if not venv_dir.exists():
            print("\n[*] JAWL Bootstrapper: Initialization.")
            print("[*] Creating virtual environment (venv).")
            venv.create(venv_dir, with_pip=True)

            venv_python = (
                venv_dir / "Scripts" / "python.exe"
                if os.name == "nt"
                else venv_dir / "bin" / "python"
            )

            if req_file.exists():
                print("[*] Upgrading pip.")
                subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                    stdout=subprocess.DEVNULL,
                    check=False,
                )

                print("\n[*] Installing dependencies from requirements.txt.\n")

                result = subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "-r", str(req_file)],
                    check=False,
                )

                # FALLBACK LOGIC
                if result.returncode != 0:
                    print("\n" + "=" * 60)
                    print(
                        "[!] Error: Failed to install dependencies (building C++/Rust packages)."
                    )
                    print("[i] You are likely using a new version of Python (e.g., 3.13),")
                    print("    for which precompiled binaries have not been released yet.")
                    print("=" * 60 + "\n")

                    answer = (
                        input(
                            "[?] Use the 'uv' package manager to automatically download \n"
                            "    a stable version of Python 3.11 and perform a fast installation? [y/N]: "
                        )
                        .strip()
                        .lower()
                    )

                    if answer in ("y", "yes", "d", "da"):
                        print("\n[*] Installing uv.")
                        subprocess.run(
                            [sys.executable, "-m", "pip", "install", "uv"], check=True
                        )

                        print("[*] Removing broken environment.")
                        shutil.rmtree(venv_dir, ignore_errors=True)

                        print("[*] uv: Creating virtual environment (Python 3.11).")
                        subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "uv",
                                "venv",
                                "--python",
                                "3.11",
                                str(venv_dir),
                            ],
                            check=True,
                        )

                        print("[*] uv: Installing dependencies.")
                        uv_result = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "uv",
                                "pip",
                                "install",
                                "--python",
                                str(venv_python),
                                "-r",
                                str(req_file),
                            ],
                            check=False,
                        )

                        if uv_result.returncode != 0:
                            print("\n[!] Critical error: uv also failed to install packages.")
                            if os.name == "nt":
                                input("Press Enter to exit.")
                            sys.exit(1)

                        print("\n[+] Dependencies successfully installed via uv.")
                    else:
                        print(
                            "\n[!] Installation aborted. It is recommended to install Python 3.11 manually."
                        )
                        if os.name == "nt":
                            input("Press Enter to exit.")
                        sys.exit(1)

                print("\n\n[*] Installation completed.\n")

        venv_python = (
            venv_dir / "Scripts" / "python.exe"
            if os.name == "nt"
            else venv_dir / "bin" / "python"
        )

        exit_code = subprocess.call(
            [str(venv_python), str(root_dir / "jawl.py")] + sys.argv[1:], env=child_env
        )

        sys.exit(exit_code)

    # =========================================================
    # If we are INSIDE the virtual environment
    # =========================================================

    sys.path.append(str(root_dir))

    try:
        from src.cli.menu import main_menu
        from src.cli.screens.logs import logs_screen
        from src.cli.screens.terminal_chat import _open_terminal_chat
        import src.main  # noqa: F401

    except ModuleNotFoundError as e:
        if os.environ.get("JAWL_RECOVERY_ATTEMPTED") == "1":
            print(
                f"\n\n[!] Critical crash: module {e.name} was still not found after reinstallation."
            )
            if os.name == "nt":
                input("Press Enter to exit.")
            sys.exit(1)

        print(f"\n\n[*] Failure: missing module {e.name}. Launching automatic recovery.")
        time.sleep(2)

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
            check=False,
        )
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=False
        )

        if result.returncode != 0:
            print("\n\n[!] Critical error: pip could not recover dependencies.")
            if os.name == "nt":
                input("Press Enter to exit.")
            sys.exit(1)

        print("\n\n[*] Dependencies successfully recovered. Launching CLI.")
        time.sleep(1)

        child_env["JAWL_RECOVERY_ATTEMPTED"] = "1"
        exit_code = subprocess.call(
            [sys.executable, str(root_dir / "jawl.py")] + sys.argv[1:], env=child_env
        )
        sys.exit(exit_code)

    log_arg = next((arg for arg in sys.argv if arg.startswith("--logs")), None)

    if log_arg:
        if "-" in log_arg:
            log_type = log_arg.split("-")[-1]
            logs_screen(log_type)
        else:
            logs_screen("main")
    elif "--terminal" in sys.argv:
        _open_terminal_chat()
    elif "--version" in sys.argv:
        print(f"JAWL Framework v{__version__}")
        sys.exit(0)
    else:
        main_menu()


if __name__ == "__main__":
    try:
        setup_and_run()
    except KeyboardInterrupt:
        print("\nОстановка загрузчика.")
        sys.exit(0)
    except Exception:
        import traceback

        print("\n[Критическая ошибка загрузчика]:")
        traceback.print_exc()
        if os.name == "nt":
            input("\nНажмите Enter для выхода.")
        sys.exit(1)
