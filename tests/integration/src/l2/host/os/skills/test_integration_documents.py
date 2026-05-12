import pytest
import docx
from src.l2_interfaces.host.os.skills.files.documents import HostOSDocuments


@pytest.mark.asyncio
async def test_integration_read_real_docx(os_client):
    """Интеграционный тест: создание физического DOCX и его чтение через навык."""
    doc_skill = HostOSDocuments(os_client)
    test_file = os_client.sandbox_dir / "real_report.docx"

    # 1. Создаем реальный физический файл через python-docx
    doc = docx.Document()
    doc.add_paragraph("JAWL Integration Test: Confidential Data.")
    doc.save(str(test_file))

    # 2. Читаем через скилл агента
    res = await doc_skill.read_document("sandbox/real_report.docx")

    assert res.is_success is True
    assert "JAWL Integration Test: Confidential Data." in res.message
