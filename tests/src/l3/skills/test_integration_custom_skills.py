import pytest
import shutil
from pathlib import Path

from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.skills.files.writer import HostOSWriter
from src.l2_interfaces.host.os.skills.execution import HostOSExecution

from src.l2_interfaces.meta.client import MetaClient
from src.l2_interfaces.meta.skills.level_creator import MetaCreator

from src.l3_agent.skills.custom import CustomSkillsRegistry
from src.l3_agent.skills.registry import execute_skill, clear_registry, register_instance
from src.l3_agent.skills.schema import ActionCall
from src.utils._tools import get_project_root


@pytest.mark.asyncio
async def test_integration_agent_self_extension(tmp_path: Path):
    """
    Хардкорный интеграционный тест: Агент сам пишет код и превращает его в навык.
    Проверяет связку: HostOSWriter -> MetaCreator -> CustomSkillsRegistry -> Pydantic Guard -> HostOSExecution RPC.
    """
    clear_registry()

    # 1. ПОДГОТОВКА СРЕДЫ
    real_root = get_project_root()
    template_src = real_root / "src" / "utils" / "templates" / "rpc_wrapper.py"
    template_dst = tmp_path / "src" / "utils" / "templates" / "rpc_wrapper.py"
    template_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_src, template_dst)

    # 2. ИНИЦИАЛИЗАЦИЯ ИНТЕРФЕЙСОВ
    # Даем агенту права ROOT (3), чтобы он мог выполнять код
    os_config = HostOSConfig(access_level=HostOSAccessLevel.ROOT, execution_timeout_sec=5)
    os_client = HostOSClient(
        base_dir=tmp_path, config=os_config, state=HostOSState(), timezone=3
    )

    # Регистрируем выполнение и запись файлов
    writer = HostOSWriter(os_client)
    executor = HostOSExecution(os_client)
    register_instance(writer)
    register_instance(executor)

    # Настраиваем реестр кастомных скиллов и интерфейс Meta
    custom_registry = CustomSkillsRegistry(data_dir=tmp_path)
    meta_client = MetaClient(
        agent_state=None,
        event_bus=None,
        settings_path=None,
        interfaces_path=None,
        access_level=3,
        available_models=[],
        custom_skills_enabled=True,
    )
    creator = MetaCreator(meta_client, custom_registry)
    register_instance(creator)

    # 3. ШАГ 1: АГЕНТ ПИШЕТ СКРИПТ В ПЕСОЧНИЦУ
    script_code = """
def calculate_crypto_tax(profit: float, rate: float = 13.0) -> dict:
    tax = profit * (rate / 100)
    net = profit - tax
    return {"gross": profit, "tax": tax, "net": net}
"""
    await writer.write_file("crypto_math.py", script_code)

    # 4. ШАГ 2: АГЕНТ РЕГИСТРИРУЕТ НАВЫК ЧЕРЕЗ META-ИНТЕРФЕЙС
    reg_action = ActionCall(
        tool_name="MetaCreator.register_custom_skill",
        parameters={
            "skill_name": "crypto_tax",
            "description": "Считает налоги на крипту.",
            "filepath": "crypto_math.py",
            "func_name": "calculate_crypto_tax",
            "parameters_dict": {"profit": "float", "rate": "float = 13.0"},
        },
    )
    reg_report = await execute_skill([reg_action])

    assert "успешно зарегистрирован" in reg_report
    assert "Custom.crypto_tax" in reg_report

    # 5. ШАГ 3: АГЕНТ ВЫЗЫВАЕТ СВОЙ НОВЫЙ НАВЫК (И МЫ ПРОВЕРЯЕМ TYPE COERCION)
    # Передаем 'profit' как строку, чтобы Pydantic Guard Layer конвертировал её во float
    exec_action = ActionCall(
        tool_name="Custom.crypto_tax",
        parameters={"profit": "1000.0"},  # LLM ошиблась и прислала строку
    )

    exec_report = await execute_skill([exec_action])

    # 6. ПРОВЕРКА РЕЗУЛЬТАТОВ (ACSERTS)
    assert "Action [Custom.crypto_tax]" in exec_report
    assert "870.0" in exec_report  # net (1000 - 13%)
    assert "130.0" in exec_report  # tax

    # Убеждаемся, что RPC обертка отработала нормально
    assert "Возвращенный результат" in exec_report
