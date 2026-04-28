from src.l2_interfaces.email.utils import decode_mime_header, strip_html_tags


def test_decode_mime_header():
    """Тест: корректное декодирование заголовков."""
    # Обычный текст
    assert decode_mime_header("Simple Subject") == "Simple Subject"
    # Base64 UTF-8 (Тема: "Привет")
    assert decode_mime_header("=?UTF-8?B?0J/RgNC40LLQtdGC?=") == "Привет"
    # Quoted-Printable UTF-8 (Тема: "Test")
    assert decode_mime_header("=?utf-8?q?Test?=") == "Test"


def test_strip_html_tags():
    """Тест: очистка HTML от тегов."""
    html = "<html><body><h1>Title</h1><p>Some text<br>More text</p></body></html>"
    clean = strip_html_tags(html)
    
    assert "Title" in clean
    assert "Some text" in clean
    assert "<h1>" not in clean
    assert "<body>" not in clean