"""
First Boot Onboarding Screen.

Guides the user through an interactive questionnaire on the very first boot.
Asks for agent name, LLM endpoints, API keys, and swarm subagents preferences.
Generates initial .env and configuration YAMLs automatically.
"""

import shutil
from pathlib import Path

import questionary
from ruamel.yaml import YAML

from src.cli.widgets.ui import (
    clear_screen,
    get_custom_style,
    print_error,
    print_info,
    print_success,
    set_window_title,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE = ROOT_DIR / ".env.example"
SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"
SETTINGS_EXAMPLE = ROOT_DIR / "config" / "settings.example.yaml"


def _ensure_base_files_exist() -> bool:
    """Creates mandatory config files from templates if missing."""
    files_to_check = [
        (ENV_FILE, ENV_EXAMPLE),
        (SETTINGS_FILE, SETTINGS_EXAMPLE),
        (
            ROOT_DIR / "config" / "interfaces.yaml",
            ROOT_DIR / "config" / "interfaces.example.yaml",
        ),
    ]

    for target, example in files_to_check:
        if not target.exists():
            if example.exists():
                shutil.copy2(example, target)
                print_info(f" Created base file {target.name}")
            else:
                print_error(f"Critical Error: Template {example.name} not found.")
                return False
    return True


def _update_env_file(key_map: dict) -> None:
    """Updates targeted keys in the local .env file."""
    try:
        with open(ENV_FILE, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(ENV_FILE, "r", encoding="cp1251") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        matched = False
        for key, value in key_map.items():
            if line.startswith(f"{key}="):
                new_lines.append(f'{key}="{value}"\n')
                matched = True
                break
        if not matched:
            new_lines.append(line)

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _update_settings_yaml(updates: dict) -> None:
    """Updates targeted keys in settings.yaml."""
    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = yaml.load(f)

        for path_keys, new_val in updates.items():
            target = data
            for k in path_keys[:-1]:
                target = target[k]
            target[path_keys[-1]] = new_val

        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
    except Exception as e:
        print_error(f"Error saving settings.yaml: {e}")


def _is_onboarding_needed() -> bool:
    """Triggers if .env or LLM_API_KEY_1 are empty."""
    if not ENV_FILE.exists():
        return True

    try:
        with open(ENV_FILE, "r", encoding="utf-8-sig") as f:
            content = f.read()
            if 'LLM_API_KEY_1=""' in content or "LLM_API_KEY_1=\n" in content:
                if "127.0.0.1" in content or "localhost" in content or "0.0.0.0" in content:
                    return False
                return True
    except Exception:
        return True

    return False


def run_onboarding_if_needed() -> bool:
    """
    First-time onboarding questionnaire loop.
    """

    if not _is_onboarding_needed():
        return True

    set_window_title("JAWL - Initial Setup")
    clear_screen()
    print_info(" Welcome to JAWL. It seems this is your first startup.")
    print_info(" Let's complete the basic system configuration.\n")

    if not _ensure_base_files_exist():
        return False

    style = get_custom_style()

    print("\n")
    agent_name = questionary.text(
        "What should we name your agent? (Leave empty for 'Agent'):", style=style
    ).ask()
    if agent_name is None:
        return False
    agent_name = agent_name.strip() or "Agent"

    print("\n")
    print_info(" Language Model (LLM) Connection Setup.")
    llm_url = questionary.text(
        "Enter Base URL (e.g., for local models: 'http://127.0.0.1:11434/v1/').\nLeave empty for standard OpenAI API:",
        style=style,
    ).ask()
    if llm_url is None:
        return False

    is_local = "127.0.0.1" in llm_url or "localhost" in llm_url or "0.0.0.0" in llm_url

    llm_key = ""
    if not is_local:
        llm_key = questionary.text(
            "Enter your LLM API Key (Required for cloud models, skip for local):", style=style
        ).ask()
        if not llm_key:
            print_error("For cloud models, an API key is mandatory. Startup aborted.")
            return False
    else:
        print_info(" Local URL detected. No API key required.")
        llm_key = "local_dummy_key"

    main_model = questionary.text(
        "Enter the exact model name for the main agent (e.g., 'gemini-3.1-flash-lite', 'claude-4.6-opus'):",
        style=style,
    ).ask()
    if not main_model:
        return False

    print("\n")
    print_info(" The Swarm subsystem allows delegating complex tasks to background subagents.")
    enable_swarm = questionary.confirm(
        "Enable the subagent system (Swarm)?", default=True, style=style
    ).ask()
    if enable_swarm is None:
        return False

    env_updates = {"LLM_API_URL": llm_url.strip(), "LLM_API_KEY_1": llm_key.strip()}
    settings_updates = {
        ("identity", "agent_name"): agent_name,
        ("llm", "main_model"): main_model.strip(),
        ("system", "swarm", "enabled"): enable_swarm,
    }

    if enable_swarm:
        sub_model = questionary.text(
            "Enter LLM model name for subagents (Cheap and fast is recommended):",
            style=style,
        ).ask()
        if not sub_model:
            return False

        settings_updates[("system", "swarm", "subagent_model")] = sub_model.strip()

        print("\n")
        print_info(
            " You can specify separate API keys for subagents to avoid consuming main key quotas."
        )
        sub_url = questionary.text(
            "Base URL for subagents (leave empty to use the same as the main model):",
            style=style,
        ).ask()

        sub_key = questionary.text(
            "API Key for subagents (leave empty to use the main model key):",
            style=style,
        ).ask()

        if sub_url is not None and sub_url.strip():
            env_updates["SUB_LLM_API_URL"] = sub_url.strip()
        if sub_key is not None and sub_key.strip():
            env_updates["SUB_LLM_API_KEY_1"] = sub_key.strip()

    print("\n")
    print_info(
        " The Tree of Thoughts subsystem allows the agent to generate and evaluate multiple strategic options before executing actions, but consumes more tokens."
    )
    enable_tot = questionary.confirm(
        "Enable Tree of Thoughts?", default=True, style=style
    ).ask()

    if enable_tot is None:
        return False

    if enable_tot:
        default_tot_model = (
            sub_model.strip() if enable_swarm and sub_model else main_model.strip()
        )

        tot_model = questionary.text(
            "Enter LLM model name for Tree of Thoughts:",
            default=default_tot_model,
            style=style,
        ).ask()
        if not tot_model:
            return False

        print("\n")
        tot_mode = questionary.select(
            "Select Tree of Thoughts operating mode:",
            choices=[
                questionary.Choice(
                    "Automatic (every 5 ReAct steps + always on the first ReAct loop step)",
                    "auto",
                ),
                questionary.Choice(
                    "Manual (triggered manually by the agent via skill call)", "manual"
                ),
                questionary.Choice(
                    "Hybrid (automatically every 5 steps + manually on demand)", "hybrid"
                ),
            ],
            style=style,
            qmark="",
            instruction=" ",
        ).ask()
        if not tot_mode:
            return False

        tot_branches_str = questionary.text(
            "How many thoughts branches to generate at once? (Recommended: 2-5):",
            default="3",
            style=style,
        ).ask()
        if not tot_branches_str:
            return False

        try:
            tot_branches = int(tot_branches_str.strip())
        except ValueError:
            tot_branches = 3

        settings_updates[("system", "tree_of_thoughts", "enabled")] = True
        settings_updates[("system", "tree_of_thoughts", "model")] = tot_model.strip()
        settings_updates[("system", "tree_of_thoughts", "mode")] = tot_mode
        settings_updates[("system", "tree_of_thoughts", "branches")] = tot_branches

    print("\n")
    print_info(
        " The Subconscious subsystem delegates database consolidation, reflection, and memory pruning to background micro-processes."
    )
    enable_subc = questionary.confirm("Enable Subconscious?", default=True, style=style).ask()

    if enable_subc is None:
        return False

    if enable_subc:
        default_subc_model = (
            sub_model.strip() if enable_swarm and sub_model else main_model.strip()
        )

        subc_model = questionary.text(
            "Enter LLM model name for Subconscious (The cheapest and fastest model is highly recommended):",
            default=default_subc_model,
            style=style,
        ).ask()
        if not subc_model:
            return False

        settings_updates[("system", "subconscious", "enabled")] = True
        settings_updates[("system", "subconscious", "llm_model")] = subc_model.strip()
        settings_updates[
            ("system", "subconscious", "patterns", "consolidation", "enabled")
        ] = True
        settings_updates[("system", "subconscious", "patterns", "reflection", "enabled")] = (
            True
        )
        settings_updates[("system", "subconscious", "patterns", "forgetting", "enabled")] = (
            True
        )

    _update_env_file(env_updates)
    _update_settings_yaml(settings_updates)

    print("\n")
    print_success("Initial configuration successfully completed.")
    print_info(
        " You can modify these and other parameters later via the 'Setup Wizard' in the main menu."
    )
    return True
