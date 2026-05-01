"""
Реестр кастомных навыков (Meta Access Level 3: CREATOR).

Модуль отвечает за метапрограммирование: он читает JSON-манифест, на лету создает
Proxy-функции для скриптов из песочницы и внедряет их в глобальный реестр (registry.py)
как нативные инструменты, доступные для вызова языковой модели.
"""

import json
import inspect
from pathlib import Path
from typing import Dict, Any, Tuple

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_custom_callable, unregister_skill


class CustomSkillsRegistry:
    """
    Управляет сохранением и динамической генерацией прокси для кастомных скиллов агента.
    """

    def __init__(self, data_dir: Path) -> None:
        """
        Инициализирует менеджер кастомных скриптов.

        Args:
            data_dir: Путь к директории хранения локальных данных (Local Data Dir).
        """
        
        self.json_path = data_dir / "meta" / "custom_skills.json"
        self.json_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.json_path.exists():
            self.json_path.write_text("{}", encoding="utf-8")

    def load_and_register_all(self) -> None:
        """
        Читает манифест (JSON) и регистрирует прокси-функции в ядро агента при старте.
        """

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for skill_name, info in data.items():
                self._create_and_register_proxy(skill_name, info)

        except Exception as e:
            system_logger.error(f"[System] Ошибка загрузки кастомных скиллов: {e}")

    def _create_and_register_proxy(self, skill_name: str, info: Dict[str, Any]) -> None:
        """
        Создает асинхронную функцию-заглушку (Proxy) с фейковой сигнатурой типов.

        Args:
            skill_name: Имя функции.
            info: Словарь с метаданными (путь, параметры, докстринг).
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

        # Метапрограммирование: создаем фейковые параметры для inspect.signature
        parameters = []
        for p_name, p_desc in params_dict.items():
            is_optional = "optional" in str(p_desc).lower() or "=" in str(p_desc)
            default = None if is_optional else inspect.Parameter.empty

            # Достаем базовый тип, например "str = None" -> "str"
            base_type_str = str(p_desc).split("=")[0].strip().lower()
            real_type = type_mapping.get(base_type_str, Any)

            parameters.append(
                inspect.Parameter(
                    name=p_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                    annotation=real_type,
                )
            )

        # Функция-заглушка (Proxy), которая дергает нативный скилл HostOSExecution
        async def dynamic_proxy(**kwargs: Any) -> Any:
            from src.l3_agent.skills.registry import call_skill

            return await call_skill(
                "HostOSExecution.execute_sandbox_func",
                {"filepath": filepath, "func_name": func_name, "kwargs": kwargs},
            )

        # Приклеиваем сигнатуру
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
        Сохраняет навык в JSON манифест и регистрирует в рантайме.

        Returns:
            Tuple[Успех_операции, Новое_имя_навыка_или_текст_ошибки]
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
        Удаляет навык из манифеста и исключает его из системного промпта.

        Returns:
            Tuple[Успех_операции, Текст_ошибки]
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
        """Возвращает словарь всех сохраненных кастомных навыков."""
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
