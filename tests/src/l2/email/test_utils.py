from src.l2_interfaces.email.utils import decode_mime_header


def test_decode_mime_header():
    """Тест: корректное декодирование заголовков."""
    assert decode_mime_header("Simple Subject") == "Simple Subject"
    assert decode_mime_header("=?UTF-8?B?0J/RgNC40LLQtdGC?=") == "Привет"
    assert decode_mime_header("=?utf-8?q?Test?=") == "Test"
