from src.l2_interfaces.voice.tts.cloud.edge.state import CloudEdgeTTSState


def test_edge_state_history_limits():
    """Тест: Стейт корректно вытесняет старые генерации из истории (MRU Cache)."""
    state = CloudEdgeTTSState(history_limit=2)

    state.add_history("file1.mp3")
    state.add_history("file2.mp3")
    state.add_history("file3.mp3")  # Должен вытеснить file1.mp3

    assert len(state.history) == 2
    assert state.history[0] == "file3.mp3"
    assert state.history[1] == "file2.mp3"
    assert "file3.mp3" in state.recent_history
    assert "file1.mp3" not in state.recent_history


def test_edge_voice_manager_settings(edge_voice_manager):
    """Тест: VoiceManager корректно отдает параметры из конфига."""
    assert edge_voice_manager.main_voice == "ru-RU-SvetlanaNeural"
    assert isinstance(edge_voice_manager.allowed_voices, list)
    assert edge_voice_manager.rate == "+10%"
    assert edge_voice_manager.volume == "-5%"
    assert edge_voice_manager.pitch == "+0Hz"
