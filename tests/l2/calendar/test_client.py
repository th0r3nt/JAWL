def test_client_init_creates_file(calendar_client):
    """Тест: При запуске клиент должен создать пустой JSON, если его нет."""
    assert calendar_client.filepath.exists()
    assert calendar_client.get_all_events() == []


def test_client_add_and_update(calendar_client):
    """Тест: Сохранение и перезапись списка событий."""
    dummy_event = {"id": "123", "title": "Test", "type": "one_time", "trigger_at": 1000.0}

    calendar_client.add_event(dummy_event)
    events = calendar_client.get_all_events()

    assert len(events) == 1
    assert events[0]["title"] == "Test"

    dummy_event["title"] = "Updated Test"
    calendar_client.update_events([dummy_event])

    assert calendar_client.get_all_events()[0]["title"] == "Updated Test"
