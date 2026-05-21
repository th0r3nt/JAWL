"""
Agent Control CLI Screen.

Manages background agent processes (start, stop, status).
Validates configurations and credentials (e.g., Telethon session verification)
before launching the main execution orchestrator.
"""

import sys
import os
import shutil
import time
import subprocess
from pathlib import Path
import psutil
import asyncio
from telethon import TelegramClient
from dotenv import dotenv_values
import questionary
from pydantic import ValidationError

from src.utils.settings import load_config
from src.utils._tools import is_agent_running
from src.cli.widgets.ui import print_success, print_error, print_info, wait_for_enter
from src.cli.screens.onboarding import run_onboarding_if_needed

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PID_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.pid"
ENV_FILE = ROOT_DIR / ".env"
MAIN_SCRIPT = ROOT_DIR / "src" / "main.py"
STOP_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.stop"
PROMPTS_DIR = ROOT_DIR / "src" / "l3_agent" / "prompt" / "personality"


def _is_agent_running() -> bool:
    """Checks if the agent process is actually running."""
    return is_agent_running()


def _check_and_setup_prompts() -> None:
    """Verifies personality prompts presence. Recreates from .example.md if missing."""
    if not PROMPTS_DIR.exists():
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    for example_file in PROMPTS_DIR.rglob("*.example.md"):
        target_name = example_file.name.replace(".example.md", ".md")
        target_file = example_file.with_name(target_name)

        if not target_file.exists():
            shutil.copy(example_file, target_file)
            print_info(f" Created base personality file: {target_name}")


def _validate_configs() -> bool:
    """Pre-flight configuration validation."""
    try:
        load_config()
        return True

    except ValidationError as e:
        print_error("Configuration structure error (yaml does not match the schema):")
        for err in e.errors():
            loc = " -> ".join(map(str, err.get("loc", [])))
            print_info(f"[{loc}]: {err.get('msg')}")

        print_info(
            "\n 💡 Tip: if you updated JAWL, delete old settings.yaml and interfaces.yaml files in the config/ folder so the system can recreate them from the latest templates."
        )
        return False

    except Exception as e:
        print_error(f"Critical error reading settings: {e}")
        return False


def _telethon_auth_flow() -> bool:
    """Pre-flight Telethon session authorization if enabled."""
    settings, interfaces = load_config()

    if not interfaces.telegram.telethon.enabled:
        return True

    env_dict = dotenv_values(ENV_FILE, encoding="utf-8-sig")
    api_id = env_dict.get("TELETHON_API_ID")
    api_hash = env_dict.get("TELETHON_API_HASH")

    if not api_id or not api_hash:
        print_info(" Telethon requires API_ID and API_HASH (obtainable at my.telegram.org).")
        api_id_input = questionary.text("Enter TELETHON_API_ID:").ask()
        if not api_id_input:
            print_error("Startup cancelled: TELETHON_API_ID is required.")
            return False

        api_hash_input = questionary.text("Enter TELETHON_API_HASH:").ask()
        if not api_hash_input:
            print_error("Startup cancelled: TELETHON_API_HASH is required.")
            return False

        with open(ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f'\nTELETHON_API_ID="{api_id_input.strip()}"\n')
            f.write(f'TELETHON_API_HASH="{api_hash_input.strip()}"\n')

        api_id = api_id_input.strip()
        api_hash = api_hash_input.strip()

    session_name = interfaces.telegram.telethon.session_name
    session_dir = (
        ROOT_DIR / "src" / "utils" / "local" / "data" / "interfaces" / "telegram" / "telethon"
    )
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / session_name

    async def _auth() -> bool:
        try:
            clean_api_id = int(api_id) if str(api_id).isdigit() else api_id
            client = TelegramClient(str(session_path), clean_api_id, api_hash)

            await client.connect()
            if not await client.is_user_authorized():
                print_info(" Telegram session not found. Authorization required.")
                await client.start()

            me = await client.get_me()
            name = me.first_name or "Unknown"
            if getattr(me, "last_name", None):
                name += f" {me.last_name}"

            print_success(f"Telegram session active (User: {name}).")
            await client.disconnect()
            return True

        except Exception as e:
            print_error(f"Error authorizing Telethon: {e}")
            return False

    print_info(" Verifying Telegram (Telethon) session...")
    return asyncio.run(_auth())


def start_agent_screen() -> None:
    """Agent startup screen."""
    if _is_agent_running():
        print_error("Agent is already running. If it's frozen, stop it first.")
        wait_for_enter()
        return

    if not run_onboarding_if_needed():
        wait_for_enter()
        return

    _check_and_setup_prompts()

    if not _validate_configs():
        wait_for_enter()
        return

    if not _telethon_auth_flow():
        wait_for_enter()
        return

    print("\n")
    print_info(" Initializing agent systems.")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONIOENCODING"] = "utf-8"

    kwargs = {"close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
    else:
        kwargs["start_new_session"] = True

    crash_log_path = ROOT_DIR / "logs" / "startup" / "startup_error.log"
    crash_log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        f_err = open(crash_log_path, "w", encoding="utf-8")

        try:
            process = subprocess.Popen(
                [sys.executable, str(MAIN_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=f_err,
                cwd=str(ROOT_DIR),
                env=env,
                **kwargs,
            )

        finally:
            f_err.close()

        time.sleep(5)

        if process.poll() is not None:
            print_error("Agent terminated with an error immediately after startup.")

            error_output = crash_log_path.read_text(encoding="utf-8", errors="replace").strip()

            if error_output:
                print_info("Critical error details (Traceback):")
                print(f"\n{error_output}\n")
            else:
                print_info("Check the main log (logs/system.log) for details.")

            wait_for_enter()
            return

        print_success("Agent successfully started in the background.")
        time.sleep(1)
        print_info(" To view logs, select 'Logs' from the main menu.")

    except Exception as e:
        print_error(f"Failed to start agent: {e}")

    wait_for_enter()


def stop_agent_screen() -> None:
    """Agent stop screen."""
    if not _is_agent_running():
        print_info(" Agent is not currently running.")
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except Exception:
            pass
        wait_for_enter()
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        process = psutil.Process(pid)

        print_info(" Sending signal for graceful shutdown.")
        STOP_FILE.touch(exist_ok=True)

        timeout = 15
        is_dead = False

        for _ in range(timeout):
            if not process.is_running():
                is_dead = True
                break
            time.sleep(1)

        if is_dead:
            print_success("Agent successfully stopped.")
        else:
            print_error(
                f"Agent did not respond within {timeout} seconds. Forcing termination (SIGKILL)."
            )
            process.kill()
            print_success("Agent process tracked and killed.")

    except Exception as e:
        print_error(f"Error attempting to stop agent: {e}")

    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
        if STOP_FILE.exists():
            STOP_FILE.unlink()
    except Exception:
        pass

    wait_for_enter()
