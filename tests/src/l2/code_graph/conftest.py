import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from src.l2_interfaces.code_graph.state import CodeGraphState
from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l1_databases.graph.management.crud_ast import GraphASTCRUD
from src.l1_databases.vector.management.code_ast import VectorCodeAST
from src.l2_interfaces.host.os.client import HostOSClient


@pytest.fixture
def cg_state(tmp_path: Path):
    return CodeGraphState(data_dir=tmp_path)


@pytest.fixture
def mock_host_os():
    os_mock = MagicMock(spec=HostOSClient)
    # Настраиваем гейткипер, чтобы он пропускал пути в тестах
    os_mock.validate_path = MagicMock(side_effect=lambda p, **kw: Path(p))
    os_mock.framework_dir = Path("JAWL")
    return os_mock


@pytest.fixture
def cg_client(cg_state, mock_host_os):
    return CodeGraphClient(state=cg_state, host_os=mock_host_os)


@pytest.fixture
def mock_graph_crud():
    crud = MagicMock(spec=GraphASTCRUD)
    crud.upsert_node = AsyncMock()
    crud.link_nodes = AsyncMock()
    crud.get_dependencies = AsyncMock(return_value=[])
    crud.get_usages = AsyncMock(return_value=[])
    crud.delete_project = AsyncMock()
    return crud


@pytest.fixture
def mock_vector_crud():
    crud = MagicMock(spec=VectorCodeAST)
    crud.save_doc = AsyncMock()
    crud.search = AsyncMock(return_value=[])
    crud.delete_project = AsyncMock()
    return crud
