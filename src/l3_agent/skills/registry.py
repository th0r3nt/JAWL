"""
Global Skills Registry and Guard Layer.

Handles registration of native and custom functions, dynamic creation of Pydantic
models for argument validation (protection against LLM hallucinations), and
Role-Based Access Control (RBAC) for subagents.
"""

import inspect
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, TypeVar, List
import logging

from pydantic import create_model, BaseModel, ValidationError

from src.utils.logger import agent_logger
from src.utils._tools import truncate_text
from src.utils.settings import SubconsciousConfig

from src.l3_agent.skills.schema import ActionCall
from src.l3_agent.swarm.roles import SubagentRole
from src.l3_agent.subconscious.schema import Pattern


@dataclass
class SkillResult:
    """
    Standardized response of any agent tool.
    """

    is_success: bool
    message: str
    terminate_loop: bool = False

    @classmethod
    def ok(cls, message: str, terminate_loop: bool = False) -> "SkillResult":
        return cls(is_success=True, message=message, terminate_loop=terminate_loop)

    @classmethod
    def fail(cls, message: str) -> "SkillResult":
        return cls(is_success=False, message=message, terminate_loop=False)


class ExecutionResult(str):
    """
    Extends str to carry an optional loop termination flag.
    Ensures 100% backward compatibility with string operations while
    allowing the ReAct loop to detect when a skill requests early exit.
    """

    terminate_loop: bool

    def __new__(cls, value: str, terminate_loop: bool = False):
        obj = super().__new__(cls, value)
        obj.terminate_loop = terminate_loop
        return obj


async def execute_skill(
    actions: List[ActionCall], logger: logging.Logger = agent_logger
) -> ExecutionResult:
    """
    Asynchronously and parallelly executes an array of requested agent actions.

    Args:
        actions: List of ActionCall objects.
        logger: Destination logger (defaults to agent_logger).
    """
    if not actions:
        return ExecutionResult("Cycle completed: no actions provided.")

    tasks = []
    for act in actions:
        name = act.tool_name
        params = act.parameters
        tasks.append(call_skill(name, params, logger=logger))

    results = await asyncio.gather(*tasks)

    should_terminate = any(getattr(res, "terminate_loop", False) for res in results)
    report = [f"* {actions[i].tool_name}: {res.message}" for i, res in enumerate(results)]

    return ExecutionResult("\n".join(report), terminate_loop=should_terminate)


_REGISTRY: Dict[str, Dict[str, Any]] = {}


def clear_registry() -> None:
    """Clears the global registry (called during agent reboot)."""
    _REGISTRY.clear()


def unregister_skill(skill_name: str) -> None:
    """Removes a skill from the registry by name."""
    if skill_name in _REGISTRY:
        del _REGISTRY[skill_name]


def _build_skill_name(
    func: Callable[..., Any], override: Optional[str] = None, instance: Optional[Any] = None
) -> str:
    """
    Generates a clean function name (removing system prefixes like src.l2_interfaces...).
    """

    if override:
        return override

    if instance:
        return f"{instance.__class__.__name__}.{func.__name__}"

    segments = func.__module__.split(".")
    useless = {"src", "l0_state", "l1_databases", "l2_interfaces", "skills", "l3_agent"}
    clean_segments = [s for s in segments if s not in useless]

    return ".".join(clean_segments) + f".{func.__name__}"


def _create_pydantic_guard(func: Callable[..., Any], skill_name: str) -> type[BaseModel]:
    """
    Dynamically generates a Pydantic model (Guard) based on the function signature (type-hints).
    Provides Type Coercion and protects against junk parameters.
    """

    sig = inspect.signature(func)
    fields = {}

    for name, param in sig.parameters.items():
        if name == "self":
            continue

        annotation = (
            param.annotation if param.annotation is not inspect.Parameter.empty else Any
        )
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[name] = (annotation, default)

    safe_name = skill_name.replace(".", "_") + "_Guard"
    return create_model(safe_name, **fields)


def _register_callable(
    func: Callable[..., Any],
    override: Optional[str] = None,
    instance: Optional[Any] = None,
    swarm: Optional[List[SubagentRole]] = None,
    subconscious: Optional[List[Pattern]] = None,
    hidden: bool = False,
) -> None:
    """
    Internal method to register a Python function in the registry.
    """

    skill_name = _build_skill_name(func, override, instance)
    sig = inspect.signature(func)

    formatted_params = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        param_str = str(param)
        if param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            param_str += " <REQ>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    raw_doc = inspect.getdoc(func) or "No description."
    clean_doc = " ".join(raw_doc.split())

    doc_str = f"{skill_name}{clean_sig} - {clean_doc}"

    _REGISTRY[skill_name] = {
        "func": func,
        "guard": _create_pydantic_guard(func, skill_name),
        "instance": instance,
        "doc_string": doc_str,
        "is_custom": False,
        "swarm": swarm or [],
        "subconscious": subconscious or [],
        "hidden": hidden,
    }
    log = f"[Skills] Registered skill: {skill_name}"
    agent_logger.debug(log)


def register_custom_callable(
    func: Callable[..., Any], skill_name: str, description: str, filepath: str
) -> None:
    """
    Registers a custom proxy skill (script from the sandbox).
    """

    sig = inspect.signature(func)
    formatted_params = []
    for name, param in sig.parameters.items():
        param_str = f"{name}: {param.annotation.__name__ if hasattr(param.annotation, '__name__') else param.annotation}"
        if param.default is inspect.Parameter.empty:
            param_str += " <REQ>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    clean_doc = " ".join(description.split())
    doc_str = f"`{skill_name}{clean_sig}` - {clean_doc} [File: {filepath}]"

    _REGISTRY[skill_name] = {
        "func": func,
        "guard": _create_pydantic_guard(func, skill_name),
        "instance": None,
        "doc_string": doc_str,
        "is_custom": True,
        "swarm": [],
        "subconscious": [],
        "hidden": False,
    }
    log = f"[Skills] Registered custom skill: {skill_name}"
    agent_logger.info(log)


F = TypeVar("F", bound=Callable[..., Any])


def skill(
    name_override: Optional[str] = None,
    swarm: Optional[List[SubagentRole]] = None,
    subconscious: Optional[List[Pattern]] = None,
    hidden: bool = False,
) -> Callable[[F], F]:
    """
    Decorator that automatically registers a new skill for the agent.
    Extracts docstring, arguments, and their types, forming the context block 'function(arg1: type) - docstring'.

    Args:
        name_override: Name override (defaults to 'Class.func_name').
        swarm: Array of subagents authorized to invoke this skill (RBAC).
        subconscious: Array of subconscious patterns authorized to invoke this skill.
        hidden: If True, hides the skill from the main agent prompt (useful for system-only tasks).
    """

    def decorator(func: F) -> F:
        sig = inspect.signature(func)
        if "self" in sig.parameters:
            setattr(func, "__is_skill__", True)
            setattr(func, "__skill_name_override__", name_override)
            setattr(func, "__swarm__", swarm)
            setattr(func, "__subconscious__", subconscious)
            setattr(func, "__skill_hidden__", hidden)
            return func
        _register_callable(
            func, name_override, swarm=swarm, subconscious=subconscious, hidden=hidden
        )
        return func

    return decorator


def register_instance(instance: Any) -> None:
    """Registers all decorated methods inside the passed class instance."""
    for attr_name in dir(instance):
        method = getattr(instance, attr_name)
        if callable(method) and getattr(method, "__is_skill__", False):
            override = getattr(method, "__skill_name_override__", None)
            swarm = getattr(method, "__swarm__", None)
            subconscious = getattr(method, "__subconscious__", None)
            hidden = getattr(method, "__skill_hidden__", False)
            _register_callable(
                method,
                override,
                instance,
                swarm=swarm,
                subconscious=subconscious,
                hidden=hidden,
            )


def get_skills_library(subconscious_config: Optional[SubconsciousConfig] = None) -> str:
    """
    Collects all skills. Automatically hides skills if they are delegated to
    an active subconscious pattern to offload the Orchestrator's context.
    """
    active_docs = []
    custom_docs = []

    for skill_name in sorted(_REGISTRY.keys()):
        data = _REGISTRY[skill_name]

        if data.get("hidden", False):
            continue

        if data.get("is_custom"):
            custom_docs.append(data["doc_string"])
            continue

        # Dynamic Visibility for Subconscious
        if subconscious_config and subconscious_config.enabled:
            patterns_list = data.get("subconscious", [])
            if patterns_list:
                is_used_by_active_pattern = False
                for p in patterns_list:
                    p_cfg = getattr(subconscious_config.patterns, p.value, None)
                    if p_cfg and p_cfg.enabled:
                        is_used_by_active_pattern = True
                        break

                if is_used_by_active_pattern:
                    continue

        func = data["func"]
        instance = data["instance"]
        doc = data["doc_string"]

        req_level = getattr(func, "__required_os_level__", None)
        if req_level is not None and instance is not None:
            host_os = getattr(instance, "host_os", None)
            if host_os is not None and host_os.access_level.value < req_level:
                continue

        visibility_check = getattr(func, "__visibility_check__", None)
        if visibility_check and instance is not None:
            try:
                if not visibility_check(instance):
                    continue
            except Exception as e:
                agent_logger.warning(
                    f"[Skills Registry] Exception in __visibility_check__ for {skill_name}: {e}"
                )

        active_docs.append(doc)

    formatted_docs = []
    last_prefix = ""
    for doc in active_docs:
        skill_name_match = doc.split("(", 1)[0].replace("`", "")
        prefix = skill_name_match.split(".")[0] if "." in skill_name_match else ""

        if last_prefix and prefix != last_prefix:
            formatted_docs.append("")

        formatted_docs.append(doc)
        last_prefix = prefix

    base = "\n".join(formatted_docs)
    if custom_docs:
        base += "\n\n### CUSTOM SKILLS\n" + "\n".join(custom_docs)
    return base


async def call_skill(
    name: str, params: Dict[str, Any], logger: logging.Logger = agent_logger
) -> SkillResult:
    """
    Low-level call of an individual skill passing parameters through the Pydantic Guard Layer.
    """
    params_str = truncate_text(str(params), max_chars=250, suffix="... [Params truncated]")

    logger.info(f"[Agent Action] {name}({params_str})")

    item = _REGISTRY.get(name)
    if not item:
        err_msg = f"Skill '{name}' not found."
        logger.warning(f"[Agent Action Result] {err_msg}")
        return SkillResult.fail(err_msg)

    func = item["func"]
    guard_model = item["guard"]

    try:
        validated_params = guard_model(**params)
        clean_kwargs = validated_params.model_dump()
    except ValidationError as e:
        errors = [
            f"- Parameter '{err['loc'][0] if err['loc'] else 'unknown'}': {err['msg']}"
            for err in e.errors()
        ]
        err_msg = "Parameter validation error:\n" + "\n".join(errors)
        logger.warning(f"[Guard] Rejected call {name}: Type error.")
        return SkillResult.fail(err_msg)

    try:
        result = await func(**clean_kwargs)
        res_msg = truncate_text(
            str(result.message), max_chars=200, suffix="... [Result truncated for logs]"
        )
        status = "Success" if result.is_success else "Fail"

        logger.info(f"[Agent Action Result] {name} ({status}): {res_msg}")
        return result
    except Exception as e:
        logger.error(f"[Agent Action Result] Error in skill {name}: {str(e)}")
        return SkillResult.fail(f"Internal skill error: {str(e)}")
