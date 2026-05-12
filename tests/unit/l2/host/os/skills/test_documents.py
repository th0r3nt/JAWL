import pytest
import docx
from unittest.mock import patch, MagicMock

from src.l2_interfaces.host.os.skills.files.documents import HostOSDocuments
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.mark.asyncio
async def test_read_document_unsupported_ext(os_client):
    """Тест: Защита от попыток скормить навыку обычный текст или бинарники."""
    doc_skill = HostOSDocuments(os_client)

    test_file = os_client.sandbox_dir / "secret.txt"
    test_file.touch()

    res = await doc_skill.read_document("sandbox/secret.txt")

    assert res.is_success is False
    assert "не поддерживается этим навыком" in res.message


@pytest.mark.asyncio
async def test_read_document_path_traversal(os_client):
    """Тест: Гейткипер отсекает попытки прочитать PDF за пределами песочницы."""
    os_client.access_level = HostOSAccessLevel.SANDBOX
    doc_skill = HostOSDocuments(os_client)

    res = await doc_skill.read_document("../../../etc/passwords.pdf")

    assert res.is_success is False
    assert "Доступ разрешен строго внутри sandbox" in res.message


@pytest.mark.asyncio
async def test_read_document_docx_success(os_client):
    """Тест: Успешное чтение реального файла .docx."""
    doc_skill = HostOSDocuments(os_client)
    test_file = os_client.sandbox_dir / "report.docx"

    # Создаем реальный DOCX файл прямо в песочнице
    doc = docx.Document()
    doc.add_paragraph("Секретный отчет для агента JAWL.")
    doc.save(str(test_file))

    res = await doc_skill.read_document("sandbox/report.docx")

    assert res.is_success is True
    assert "Секретный отчет для агента JAWL." in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.files.documents.pypdf")
async def test_read_document_pdf_pagination(mock_pypdf, os_client):
    """Тест: Мокаем pypdf и проверяем логику пагинации."""
    doc_skill = HostOSDocuments(os_client)
    test_file = os_client.sandbox_dir / "book.pdf"
    test_file.touch()  # Пустышка, чтобы пройти is_file()

    # Настраиваем мок-читалку PDF
    mock_reader = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Текст страницы 1."
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Текст страницы 2."
    mock_page3 = MagicMock()
    mock_page3.extract_text.return_value = "Текст страницы 3."

    # Имитируем массив страниц
    mock_reader.pages = [mock_page1, mock_page2, mock_page3]
    mock_pypdf.PdfReader.return_value = mock_reader

    # 1. Читаем всё
    res_full = await doc_skill.read_document("sandbox/book.pdf")
    assert res_full.is_success is True
    assert "Текст страницы 1" in res_full.message
    assert "Текст страницы 3" in res_full.message

    # 2. Читаем только 2-ю страницу (start=2, end=2)
    res_paginated = await doc_skill.read_document("sandbox/book.pdf", page_start=2, page_end=2)
    assert res_paginated.is_success is True
    assert "Текст страницы 1" not in res_paginated.message
    assert "Текст страницы 2" in res_paginated.message
    assert "Текст страницы 3" not in res_paginated.message

    # 3. Выход за пределы массива
    res_oob = await doc_skill.read_document("sandbox/book.pdf", page_start=5)
    assert res_oob.is_success is False
    assert "Неверный диапазон" in res_oob.message


@pytest.mark.asyncio
async def test_read_document_truncation_limit(os_client):
    """Тест: Защита контекстного окна. Длинный документ жестко обрезается."""
    doc_skill = HostOSDocuments(os_client)

    # Ставим жесткий лимит в 50 символов
    os_client.config.file_read_max_chars = 50
    test_file = os_client.sandbox_dir / "long.docx"

    doc = docx.Document()
    doc.add_paragraph("A" * 500)  # Текст на 500 символов
    doc.save(str(test_file))

    res = await doc_skill.read_document("sandbox/long.docx")

    assert res.is_success is True
    assert "Текст обрезан" in res.message
    # Проверяем, что итоговое сообщение не раздулось больше 150 симв. (с учетом Markdown заголовка скилла)
    assert len(res.message) < 150
