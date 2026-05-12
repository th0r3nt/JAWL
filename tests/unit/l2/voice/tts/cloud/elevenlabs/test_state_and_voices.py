from src.l2_interfaces.voice.tts.cloud.elevenlabs.state import CloudElevenLabsTTSState


def test_elevenlabs_state_history_limits():
    """Тест: Стейт корректно вытесняет старые генерации из истории (MRU Cache)."""
    state = CloudElevenLabsTTSState(history_limit=2)

    state.add_history("file1.mp3")
    state.add_history("file2.mp3")
    state.add_history("file3.mp3")  # Должен вытеснить file1.mp3

    assert len(state.history) == 2
    assert state.history[0] == "file3.mp3"
    assert state.history[1] == "file2.mp3"
    assert "file3.mp3" in state.recent_history
    assert "file1.mp3" not in state.recent_history


def test_voice_manager_settings(el_voice_manager):
    """Тест: VoiceManager корректно отдает параметры для API."""
    settings = el_voice_manager.get_voice_settings()

    assert settings["stability"] == 0.4
    assert settings["similarity_boost"] == 0.9
