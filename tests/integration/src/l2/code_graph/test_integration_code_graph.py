import pytest
from pathlib import Path
from unittest.mock import patch

from src.utils.settings import HostOSConfig, CodeGraphConfig
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel

from src.l1_databases.graph.manager import GraphManager
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.vector.db import VectorDB

from src.l2_interfaces.code_graph.state import CodeGraphState
from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l2_interfaces.code_graph.skills.indexing import CodeGraphIndexing
from src.l2_interfaces.code_graph.skills.navigation import CodeGraphNavigation


class DummyEmbeddingModel:
    """Заглушка для эмбеддингов, чтобы не качать тяжелую ONNX-модель в тестах."""

    async def get_embedding(self, text: str) -> list[float]:
        # Делаем примитивный семантический вектор: если есть слово "секрет", вектор другой
        if "секрет" in text.lower():
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]


@pytest.fixture
async def setup_integration_env(tmp_path: Path):
    """Поднимает реальные БД и интерфейсы во временной директории."""

    # 1. Поднимаем гейткипер ОС
    os_config = HostOSConfig(access_level=HostOSAccessLevel.SANDBOX)
    os_client = HostOSClient(
        base_dir=tmp_path, config=os_config, state=HostOSState(), timezone=3
    )

    # 2. Поднимаем Графовую базу
    graph_manager = GraphManager(db_path=tmp_path / "kuzu_db")
    await graph_manager.connect()

    # 3. Поднимаем Векторную базу (с мокнутой легкой моделью, размер вектора = 3)
    # Используем patch, чтобы VectorManager не пытался качать реальные веса FastEmbed
    with patch(
        "src.l1_databases.vector.manager.EmbeddingModel", return_value=DummyEmbeddingModel()
    ):
        vector_manager = VectorManager(
            db_path=tmp_path / "qdrant_db",
            embedding_model_path=tmp_path / "models",
            embedding_model_name="mock",
            vector_size=3,
            similarity_threshold=0.5,
        )

    # Вместо VectorManager.connect() инициализируем Qdrant напрямую, чтобы прокинуть нужный vector_size
    vector_manager.db = VectorDB(
        db_path=str(tmp_path / "qdrant_db"),
        collections=["knowledge", "thoughts", "code_ast"],
        vector_size=3,
    )
    await vector_manager.db.connect()

    # Обновляем ссылки в CRUD-контроллерах, так как мы подменили db
    vector_manager.code_ast.db = vector_manager.db
    vector_manager.knowledge.db = vector_manager.db
    vector_manager.thoughts.db = vector_manager.db

    # 4. Поднимаем интерфейс Code Graph
    cg_state = CodeGraphState(data_dir=tmp_path)
    cg_config = CodeGraphConfig(enabled=True)
    cg_client = CodeGraphClient(state=cg_state, config=cg_config, host_os=os_client)

    indexer = CodeGraphIndexing(cg_client, graph_manager.ast_crud, vector_manager.code_ast)
    navigator = CodeGraphNavigation(cg_client, graph_manager.ast_crud, vector_manager.code_ast)

    yield os_client, indexer, navigator

    # Очистка (чтобы не было Lock-ошибок Kuzu на Windows)
    await graph_manager.disconnect()
    await vector_manager.disconnect()


@pytest.mark.asyncio
async def test_code_graph_full_lifecycle(setup_integration_env):
    """
    Хардкорный тест E2E:
    Генерация кода -> AST-Индексация -> Структура -> Зависимости -> Семантический поиск -> Очистка.
    """
    os_client, indexer, navigator = setup_integration_env

    # ======================================================
    # 1. ГЕНЕРАЦИЯ ТЕСТОВОЙ КОДОВОЙ БАЗЫ
    # ======================================================
    project_dir = os_client.sandbox_dir / "test_project"
    project_dir.mkdir(parents=True)

    # Файл utils.py с классом и докстрингом
    utils_code = '''
class SecurityHelper:
    """Это секретный класс для вычислений хэшей."""
    def encrypt(self):
        pass
'''
    (project_dir / "utils.py").write_text(utils_code, encoding="utf-8")

    # Файл main.py, который импортирует utils
    main_code = """
from utils import SecurityHelper

def start_server():
    helper = SecurityHelper()
    helper.encrypt()
"""
    (project_dir / "main.py").write_text(main_code, encoding="utf-8")

    # ======================================================
    # 2. ИНДЕКСАЦИЯ
    # ======================================================

    res_index = await indexer.index_codebase("sandbox/test_project", "test_proj")

    assert res_index.is_success is True
    assert "2 файлов" in res_index.message
    assert "test_proj" in indexer.client.state.active_indexes

    # ======================================================
    # 3. ПОЛУЧЕНИЕ СТРУКТУРЫ (get_file_structure)
    # ======================================================

    res_struct = await navigator.get_file_structure("test_proj", "utils.py")

    assert res_struct.is_success is True
    assert "[CLASS] SecurityHelper" in res_struct.message
    assert "[METHOD] encrypt" in res_struct.message

    # ======================================================
    # 4. ПОИСК ЗАВИСИМОСТЕЙ (trace_dependencies)
    # ======================================================

    # Кто использует utils.py? (Должен быть main.py)
    res_deps = await navigator.trace_dependencies("test_proj", "utils.py")

    assert res_deps.is_success is True
    # Проверяем входящие связи (usages)
    assert "Его импортирует: main.py (FILE)" in res_deps.message

    # ======================================================
    # 5. СЕМАНТИЧЕСКИЙ ПОИСК (search_code_semantic)
    # ======================================================

    # Ищем класс по смыслу его докстринга (передаем слово "секрет", которое
    # в нашей мокнутой модели дает вектор [1,0,0], совпадающий с вектором докстринга).
    res_sem = await navigator.search_code_semantic("test_proj", "какой-то секрет")

    assert res_sem.is_success is True
    assert "utils.py::SecurityHelper" in res_sem.message
    assert "секретный класс" in res_sem.message

    # ======================================================
    # 6. ОЧИСТКА ИНДЕКСА (delete_index)
    # ======================================================

    res_del = await indexer.delete_index("test_proj")

    assert res_del.is_success is True
    assert "test_proj" not in indexer.client.state.active_indexes

    # Убеждаемся, что база пуста (запрос структуры должен вернуть ошибку/пустоту)
    res_struct_after = await navigator.get_file_structure("test_proj", "utils.py")
    assert res_struct_after.is_success is False
