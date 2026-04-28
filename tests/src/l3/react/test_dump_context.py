from unittest.mock import patch, MagicMock
from src.l3_agent.react.loop import ReactLoop


def test_react_dump_context_to_file(mock_dependencies):
    """Тест: Запись системного промпта в файл логов (last_prompt.md) работает безопасно."""
    loop = ReactLoop(**mock_dependencies)
    
    messages = [
        {"role": "system", "content": "You are AI"},
        {"role": "user", "content": "Hello"}
    ]
    
    # Мокаем встроенную функцию open
    with patch("builtins.open") as mock_open:
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        loop._dump_context_to_file(messages)
        
        mock_open.assert_called_once_with("logs/last_prompt.md", "w", encoding="utf-8")
        
        # Проверяем, что все сообщения были записаны
        written_content = "".join([call[0][0] for call in mock_file.write.call_args_list])
        assert "### Role: system" in written_content
        assert "You are AI" in written_content
        assert "### Role: user" in written_content
        assert "Hello" in written_content


def test_react_dump_context_exception_safety(mock_dependencies):
    """Тест: Если файл недоступен, дамп падает тихо и не ломает цикл агента."""
    loop = ReactLoop(**mock_dependencies)
    
    with patch("builtins.open", side_effect=PermissionError("Access Denied")):
        # Не должно выкинуть Exception наверх
        loop._dump_context_to_file([{"role": "system", "content": "1"}])