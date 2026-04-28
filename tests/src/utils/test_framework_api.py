import json
from unittest.mock import patch
import src.utils.framework_api_template as api


def test_framework_api_send_event(tmp_path):
    with patch("src.utils.framework_api_template.Path") as mock_path:
        mock_path.return_value.parent = tmp_path

        api.send_event("Критическая ошибка", {"module": "test"})

        files = list((tmp_path / ".jawl_events").glob("*.json"))
        # Читаем с utf-8-sig
        data = json.loads(files[0].read_text(encoding="utf-8-sig"))
        assert data["message"] == "Критическая ошибка"


def test_framework_api_update_dashboard(tmp_path):
    with patch("src.utils.framework_api_template.Path") as mock_path:
        mock_path.return_value.parent = tmp_path

        api.update_dashboard("Weather", "Sunny")

        files = list((tmp_path / ".jawl_events").glob("*.json"))
        # Читаем с utf-8-sig
        data = json.loads(files[0].read_text(encoding="utf-8-sig"))
        assert data["payload"]["name"] == "Weather"
