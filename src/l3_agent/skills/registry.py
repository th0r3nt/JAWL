import inspect
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, TypeVar

from src.utils.logger import system_logger


@dataclass
class SkillResult:
    is_success: bool
    message: str

    @classmethod
    def ok(cls, message: str) -> "SkillResult":
        return cls(is_success=True, message=message)

    @classmethod
    def fail(cls, message: str) -> "SkillResult":
        return cls(is_success=False, message=message)


_REGISTRY: Dict[str, Callable] = {}
_SKILL_DOCS: list[str] = []


def _build_skill_name(
    func: Callable, override: Optional[str] = None, instance: Optional[Any] = None
) -> str:
    """Хелпер для формирования красивого имени функции."""
    if override:
        return override

    # Если это метод класса
    if instance:
        return f"{instance.__class__.__name__}.{func.__name__}"

    # Если обычная функция
    segments = func.__module__.split(".")
    useless = {"src", "l0_state", "l1_databases", "l2_interfaces", "skills", "l3_agent"}
    clean_segments = [s for s in segments if s not in useless]
    return ".".join(clean_segments) + f".{func.__name__}"


def _register_callable(
    func: Callable, override: Optional[str] = None, instance: Optional[Any] = None
):
    """Ядро регистрации. Формирует докстринги и сохраняет ссылку на вызов."""
    
    skill_name = _build_skill_name(func, override, instance)

    sig = inspect.signature(func)

    # Формируем новую строку сигнатуры, добавляя пометку <REQUIRED> к обязательным аргументам
    formatted_params = []
    for name, param in sig.parameters.items():
        param_str = str(param)

        # Если у параметра нет дефолтного значения и это не *args / **kwargs
        if param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            param_str += " <REQUIRED>"

        formatted_params.append(param_str)

    # Вручную склеиваем в строку, что заодно избавит нас от аннотации типа возврата (-> SkillResult)
    clean_sig = f"({', '.join(formatted_params)})"

    # Убираем переносы строк из докстринга: сворачиваем всё в одну красивую строку
    raw_doc = inspect.getdoc(func) or "Без описания."
    clean_doc = " ".join(raw_doc.split())

    _SKILL_DOCS.append(f"`{skill_name}{clean_sig}` - {clean_doc}")
    _REGISTRY[skill_name] = func
    system_logger.info(f"[System] Зарегистрирован скилл: {skill_name}")


F = TypeVar("F", bound=Callable[..., Any])


def skill(name_override: Optional[str] = None) -> Callable[[F], F]:
    """Декоратор со строгой типизацией, регистрирующий функции для агента."""

    def decorator(func: F) -> F:
        sig = inspect.signature(func)

        if "self" in sig.parameters:
            setattr(func, "__is_skill__", True)
            setattr(func, "__skill_name_override__", name_override)
            return func

        _register_callable(func, name_override)
        return func

    return decorator


def register_instance(instance: Any):
    """
    Проходится по объекту класса и регистрирует все методы, помеченные @skill.
    Вызывать в main.py после создания инстансов баз/интерфейсов.
    """
    for attr_name in dir(instance):
        method = getattr(instance, attr_name)
        if callable(method) and getattr(method, "__is_skill__", False):
            override = getattr(method, "__skill_name_override__", None)
            _register_callable(method, override, instance)


def get_skills_library() -> str:
    return "\n".join(_SKILL_DOCS)


async def execute_skill(actions: list[dict]) -> str:
    if not actions:
        return "Цикл завершен: действий не передано."

    tasks = []
    for act in actions:
        name = act.get("tool_name", "unknown_tool")
        params = act.get("parameters", {})

        system_logger.info(f"[Agent Action] Вызов: {name}({params})")

        tasks.append(_run_single_skill(name, params))

    results = await asyncio.gather(*tasks)

    report = []
    for i, res in enumerate(results):
        tool_name = actions[i].get("tool_name")
        report.append(f"Action [{tool_name}]: {res.message}")

    return "\n".join(report)


async def _run_single_skill(name: str, params: dict) -> SkillResult:
    func = _REGISTRY.get(name)
    if not func:
        system_logger.info(f"[Agent Action Result] Скилл '{name}' не найден.")
        return SkillResult.fail(f"Скилл '{name}' не найден.")
    try:
        # Убираем возможный мусор, который LLM может попытаться скормить вместо параметров
        valid_params = {
            k: v for k, v in params.items() if k in inspect.signature(func).parameters
        }

        result = await func(**valid_params)
        system_logger.info(f"[Agent Action Result] {name}: {result}")

        return result

    except Exception as e:
        system_logger.info(f"[Agent Action Result] Ошибка в скилле {name}: {str(e)}")
        return SkillResult.fail(f"Ошибка: {str(e)}")
