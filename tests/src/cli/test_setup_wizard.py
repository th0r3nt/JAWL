from src.cli.screens.setup_wizard import _toggle_interface


def test_toggle_interface_existing():
    """Тест: переключение существующего флага в словаре."""
    data = {"web": {"browser": {"enabled": False}}}

    _toggle_interface(data, ["web", "browser", "enabled"])
    assert data["web"]["browser"]["enabled"] is True

    _toggle_interface(data, ["web", "browser", "enabled"])
    assert data["web"]["browser"]["enabled"] is False


def test_toggle_interface_creates_missing_keys():
    """Тест: если ключей в YAML нет, они создаются автоматически."""
    data = {}

    _toggle_interface(data, ["github", "enabled"])
    assert data["github"]["enabled"] is True
