import pytest


@pytest.mark.asyncio
async def test_look_at_media_success(vision_skills, mock_os_client, tmp_path):
    """Тест: успешное создание маркера для картинки."""
    # Создаем фейковую картинку
    fake_image = tmp_path / "test.png"
    fake_image.write_bytes(b"fake_data")

    # Мокаем гейткипер, чтобы он пропустил этот путь
    mock_os_client.validate_path.return_value = fake_image

    res = await vision_skills.look_at_media("test.png")

    assert res.is_success is True
    assert "[SYSTEM_MARKER_IMAGE_ATTACHED:" in res.message
    assert str(fake_image.resolve()) in res.message


@pytest.mark.asyncio
async def test_look_at_media_unsupported_ext(vision_skills, mock_os_client, tmp_path):
    """Тест: скилл отклоняет текстовые и другие не-медиа файлы."""
    fake_txt = tmp_path / "test.txt"
    fake_txt.write_text("not an image", encoding="utf-8")

    mock_os_client.validate_path.return_value = fake_txt

    res = await vision_skills.look_at_media("test.txt")

    assert res.is_success is False
    assert "не поддерживается" in res.message


@pytest.mark.asyncio
async def test_look_at_media_permission_error(vision_skills, mock_os_client):
    """Тест: скилл отклоняет доступ, если гейткипер не пускает."""
    mock_os_client.validate_path.side_effect = PermissionError("SANDBOX: Доступ запрещен")

    res = await vision_skills.look_at_media("/root/secret.jpg")

    assert res.is_success is False
    assert "SANDBOX: Доступ запрещен" in res.message
