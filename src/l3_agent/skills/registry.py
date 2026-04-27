import inspect
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, TypeVar

from src.utils.logger import system_logger
from src.utils._tools import truncate_text
from src.l3_agent.skills.schema import ActionCall


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


def clear_registry():
    """Очищает реестр скиллов (необходимо для чистой перезагрузки агента)."""
    _REGISTRY.clear()
    _SKILL_DOCS.clear()


def _build_skill_name(
    func: Callable, override: Optional[str] = None, instance: Optional[Any] = None
) -> str:
    """Хелпер для формирования красивого имени функции."""
    if override:
        return override

    if instance:
        return f"{instance.__class__.__name__}.{func.__name__}"

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

    formatted_params = []
    for name, param in sig.parameters.items():
        param_str = str(param)
        if param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            param_str += " <REQUIRED>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    raw_doc = inspect.getdoc(func) or "Без описания."
    clean_doc = " ".join(raw_doc.split())

    _SKILL_DOCS.append(f"`{skill_name}{clean_sig}` - {clean_doc}")
    _REGISTRY[skill_name] = func
    system_logger.info(f"[Skills] Зарегистрирован скилл: {skill_name}")


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


async def execute_skill(actions: list[ActionCall]) -> str:
    if not actions:
        return "Цикл завершен: действий не передано."

    tasks = []
    for act in actions:
        name = act.tool_name
        params = act.parameters

        # Ограничиваем длину параметров для логов
        params_str = truncate_text(
            str(params), max_chars=250, suffix="... [Параметры обрезаны]"
        )

        system_logger.info(f"[Agent Action] {name}({params_str})")
        tasks.append(_run_single_skill(name, params))

    results = await asyncio.gather(*tasks)

    report = []
    for i, res in enumerate(results):
        report.append(f"Action [{actions[i].tool_name}]: {res.message}")

    return "\n".join(report)


async def _run_single_skill(name: str, params: dict) -> SkillResult:
    """
    Выполняет одну функцию, которую вызвал агент.
    Возвращает результат вызова функции.
    """

    func = _REGISTRY.get(name)
    if not func:
        system_logger.info(f"[Agent Action Result] Скилл '{name}' не найден.")
        return SkillResult.fail(f"Скилл '{name}' не найден.")
    try:
        valid_params = {
            k: v for k, v in params.items() if k in inspect.signature(func).parameters
        }

        result = await func(**valid_params)

        # Обрезаем результат ТОЛЬКО для логов, чтобы не засорять system.log и экран CLI
        res_msg = truncate_text(
            str(result.message), max_chars=800, suffix="... [Результат обрезан для логов]"
        )
        status = "Success" if result.is_success else "Fail"
        system_logger.info(f"[Agent Action Result] {name} ({status}): {res_msg}")

        return result
    except Exception as e:
        system_logger.info(f"[Agent Action Result] Ошибка в скилле {name}: {str(e)}")
        return SkillResult.fail(f"Ошибка: {str(e)}")
