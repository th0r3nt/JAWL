import pytest
import shutil
from pathlib import Path

from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.files.writer import HostOSWriter
from src.utils._tools import get_project_root


@pytest.mark.asyncio
async def test_integration_rpc_sandbox_execution(tmp_path: Path):
    """
    Интеграционный тест: "Агент пишет код и динамически его выполняет".
    Проверяет связку: HostOSWriter -> Файловая система -> HostOSExecution -> RPC Wrapper -> JSON ответ.
    """

    # 1. Подготавливаем среду. Так как RPC-обертке нужен шаблон из исходников,
    # скопируем его во временную директорию теста, чтобы сымитировать структуру JAWL.
    real_root = get_project_root()
    template_src = real_root / "src" / "utils" / "templates" / "rpc_wrapper.py"

    template_dst = tmp_path / "src" / "utils" / "templates" / "rpc_wrapper.py"
    template_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_src, template_dst)

    # 2. Поднимаем клиент ОС с уровнем ROOT (чтобы разрешить выполнение)
    config = HostOSConfig(access_level=HostOSAccessLevel.ROOT, execution_timeout_sec=5)
    client = HostOSClient(base_dir=tmp_path, config=config, state=HostOSState(), timezone=3)

    writer = HostOSWriter(client)
    executor = HostOSExecution(client)

    # 3. Агент пишет свой кастомный скрипт в песочницу
    script_code = """
def calculate_metrics(cpu_load: int, user: str) -> dict:
    if cpu_load > 90:
        status = "critical"
    else:
        status = "normal"
    return {"user": user, "status": status, "score": cpu_load * 2}
"""
    write_res = await writer.write_file("metrics.py", script_code)
    assert write_res.is_success is True

    # 4. Агент динамически вызывает функцию из написанного им скрипта (RPC)
    rpc_res = await executor.execute_sandbox_func(
        filepath="metrics.py",
        func_name="calculate_metrics",
        kwargs={"cpu_load": 95, "user": "Admin"},
    )

    # 5. Проверяем, что RPC-обертка успешно сериализовала и вернула результат работы функции
    assert rpc_res.is_success is True
    assert "critical" in rpc_res.message
    assert "Admin" in rpc_res.message
    assert "190" in rpc_res.message  # 95 * 2
    assert "Возвращенный результат (Return)" in rpc_res.message
