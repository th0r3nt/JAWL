from unittest.mock import MagicMock
from src.l2_interfaces.host.os.polls.tree_builder import TreeBuilder


def test_tree_builder_max_depth(tmp_path):
    """Тест: генератор ASCII дерева уважает max_depth и фильтрует мусор."""

    # Создаем структуру: root -> folder1 -> folder2 -> secret.txt
    folder1 = tmp_path / "folder1"
    folder1.mkdir()

    folder2 = folder1 / "folder2"
    folder2.mkdir()
    (folder2 / "secret.txt").touch()

    # Создаем игнорируемый мусор
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".git").mkdir()

    mock_client = MagicMock()
    mock_client.get_file_metadata.return_value = {}
    mock_client.sandbox_dir = tmp_path

    builder = TreeBuilder(mock_client)

    # Глубина 0: видим только папки первого уровня
    lines_depth_0 = builder.build_tree(tmp_path, use_emojis=True, max_depth=0)
    text_0 = "\n".join(lines_depth_0)

    assert "folder1/..." in text_0  # Папка обрезана
    assert "folder2" not in text_0
    assert "__pycache__" not in text_0  # Мусор отфильтрован

    # Глубина 1: видим folder2, но не видим её содержимое
    lines_depth_1 = builder.build_tree(tmp_path, use_emojis=True, max_depth=1)
    text_1 = "\n".join(lines_depth_1)

    assert "folder2/..." in text_1
    assert "secret.txt" not in text_1

    # Глубина 2: видим всё
    lines_depth_2 = builder.build_tree(tmp_path, use_emojis=True, max_depth=2)
    text_2 = "\n".join(lines_depth_2)

    assert "secret.txt" in text_2
