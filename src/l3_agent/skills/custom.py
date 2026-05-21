"""
Custom Skills Registry (Meta Access Level 3: CREATOR).

The module is responsible for metaprogramming: it reads the JSON manifest,
creates proxy functions for sandbox scripts on the fly, and registers them into
the global registry (registry.py) as native tools available for LLM calls.
"""

import json
import inspect
import ast
from pathlib import Path
from typing import Dict, Any, Tuple

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import register_custom_callable, unregister_skill


class CustomSkillsRegistry:
    """
    Manages saving and dynamic generation of proxies for custom agent skills.
    """

    def __init__(self, data_dir: Path) -> None:
        """
        Initializes custom skills manager.

        Args:
            data_dir: Path to the local data storage directory (Local Data Dir).
        """

        self.json_path = data_dir / "interfaces" / "meta" / "custom_skills.json"
        self.json_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.json_path.exists():
            self.json_path.write_text("{}", encoding="utf-8")

    def load_and_register_all(self) -> None:
        """
        Reads the manifest (JSON) and registers proxy functions in the agent core upon startup.
        """

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for skill_name, info in data.items():
                self._create_and_register_proxy(skill_name, info)

        except Exception as e:
            main_logger.error(f"[System] Error loading custom skills: {e}")

    def _create_and_register_proxy(self, skill_name: str, info: Dict[str, Any]) -> None:
        """
        Creates an asynchronous placeholder function (Proxy) with a fake type signature.

        Args:
            skill_name: Function identifier name.
            info: Metadata dict containing filepath, parameters, and docstring.
        """

        filepath = info["filepath"]
        func_name = info["func_name"]
        description = info["description"]
        params_dict = info.get("params", {})

        type_mapping = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        # Metaprogramming: create fake parameters for inspect.signature
        parameters = []
        for p_name, p_desc in params_dict.items():
            p_str = str(p_desc).lower()
            is_optional = "optional" in p_str or "=" in p_str

            # Extract the real default value from the string (if any)
            default_val = None
            if "=" in p_str:
                try:
                    val_str = str(p_desc).split("=", 1)[1].strip()
                    default_val = ast.literal_eval(val_str)
                except Exception:
                    pass

            default = default_val if is_optional else inspect.Parameter.empty

            # Extract the base type, e.g. "float = 13.0" -> "float"
            base_type_str = str(p_desc).split("=")[0].strip().lower()
            base_type_str = base_type_str.replace("optional", "").strip()
            real_type = type_mapping.get(base_type_str, Any)

            parameters.append(
                inspect.Parameter(
                    name=p_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                    annotation=real_type,
                )
            )

        # Placeholder function (Proxy) that invokes the native HostOSExecution skill
        async def dynamic_proxy(**kwargs: Any) -> Any:
            from src.l3_agent.skills.registry import call_skill

            return await call_skill(
                "HostOSExecution.execute_sandbox_func",
                {"filepath": filepath, "func_name": func_name, "kwargs": kwargs},
            )

        # Attach signature
        dynamic_proxy.__signature__ = inspect.Signature(parameters=parameters)
        dynamic_proxy.__name__ = skill_name

        unregister_skill(skill_name)
        register_custom_callable(dynamic_proxy, skill_name, description, filepath)

    def register_skill(
        self,
        skill_name: str,
        description: str,
        filepath: str,
        func_name: str,
        params: Dict[str, str],
    ) -> Tuple[bool, str]:
        """
        Saves the skill to the JSON manifest and registers it at runtime.

        Returns:
            Tuple[bool, str]: Tuple of (operation_success, new_skill_name_or_error_text)
        """

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not skill_name.startswith("Custom."):
                skill_name = f"Custom.{skill_name}"

            info = {
                "description": description,
                "filepath": filepath,
                "func_name": func_name,
                "params": params,
            }

            data[skill_name] = info

            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            self._create_and_register_proxy(skill_name, info)
            return True, skill_name

        except Exception as e:
            return False, str(e)

    def unregister_skill(self, skill_name: str) -> Tuple[bool, str]:
        """
        Removes the skill from the manifest and excludes it from the system prompt.

        Returns:
            Tuple[bool, str]: Tuple of (operation_success, error_text)
        """

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if skill_name in data:
                del data[skill_name]
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)

            unregister_skill(skill_name)
            return True, ""

        except Exception as e:
            return False, str(e)

    def get_all_skills(self) -> Dict[str, Any]:
        """Returns a dictionary of all saved custom skills."""
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
