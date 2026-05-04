from pathlib import Path
from unittest.mock import patch

from src.cli.screens.onboarding import _is_onboarding_needed, _update_settings_yaml


def test_is_onboarding_needed_no_env(tmp_path: Path):
    """Если файла .env нет вообще - онбординг нужен."""
    with patch("src.cli.screens.onboarding.ENV_FILE", tmp_path / ".env"):
        assert _is_onboarding_needed() is True


def test_is_onboarding_needed_empty_key(tmp_path: Path):
    """Если ключ LLM пуст - онбординг нужен."""
    env_file = tmp_path / ".env"
    env_file.write_text('LLM_API_KEY_1=""\nLLM_API_URL=""\n', encoding="utf-8")
    
    with patch("src.cli.screens.onboarding.ENV_FILE", env_file):
        assert _is_onboarding_needed() is True


def test_is_onboarding_needed_local_url(tmp_path: Path):
    """Если указан локальный URL (Ollama), ключ может быть пуст - онбординг НЕ нужен."""
    env_file = tmp_path / ".env"
    env_file.write_text('LLM_API_KEY_1=""\nLLM_API_URL="http://127.0.0.1:11434"\n', encoding="utf-8")
    
    with patch("src.cli.screens.onboarding.ENV_FILE", env_file):
        assert _is_onboarding_needed() is False


def test_update_settings_yaml(tmp_path: Path):
    """Тест: функция глубоко обновляет YAML-файл, не ломая структуру."""
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text("system:\n  swarm:\n    enabled: false\n", encoding="utf-8")
    
    updates = {
        ("system", "swarm", "enabled"): True,
        ("system", "swarm", "subagent_model"): "flash"
    }
    
    with patch("src.cli.screens.onboarding.SETTINGS_FILE", settings_file):
        _update_settings_yaml(updates)
        
    content = settings_file.read_text(encoding="utf-8")
    assert "enabled: true" in content
    assert "subagent_model: flash" in content