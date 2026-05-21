"""
Тесты для L0 State модуля Cloud Whisper STT.
Проверяет логику кэширования (MRU).
"""

from src.l2_interfaces.voice.stt.cloud.whisper.state import CloudWhisperSTTState


def test_cloud_whisper_state_history_limits() -> None:
    """Тест: Стейт корректно вытесняет старые генерации из истории (MRU Cache)."""
    state = CloudWhisperSTTState(history_limit=2)

    state.add_history("audio1.mp3")
    state.add_history("audio2.wav")
    state.add_history("audio3.m4a")  # Должен вытеснить audio1.mp3

    assert len(state.history) == 2
    assert state.history[0] == "audio3.m4a"
    assert state.history[1] == "audio2.wav"

    assert "audio3.m4a" in state.recent_history
    assert "audio1.mp3" not in state.recent_history


def test_cloud_whisper_state_empty_history() -> None:
    """Тест: Форматирование emptyой истории."""
    state = CloudWhisperSTTState()
    assert "were not transcribed" in state.recent_history
