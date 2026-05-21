# Voice Interfaces Configuration (Voice)

The `voice` interface allows granting the agent hearing and a voice, turning it into a full-fledged voice assistant. It includes speech recognition (STT) and speech synthesis (TTS) subsystems.

## Speech Recognition (STT: Speech-To-Text)

The agent can receive audio and video files and extract text transcriptions from them.

### Cloud Whisper
Uses the OpenAI Whisper API (or compatible services like Groq or local vLLM).
Requires the `CLOUD_WHISPER_API_KEY` token specified in the `.env` file. If missing, the system will automatically fall back to your main `OPENAI_API_KEY`.

**Parameters (`voice.stt.cloud.whisper`):**
* **`enabled`**: `true` / `false`.
* **`model`**: Target model name (default is `"whisper-1"`).
* **`temperature`**: Generation creativity parameter (default is `0.0` for maximum accuracy).
* **`timeout_sec`**: API response timeout.

---

## Speech Synthesis (TTS: Text-To-Speech)

The agent can vocalize its responses and save them as audio files (for example, to send you voice messages in Telegram).

### Microsoft Edge (Free)
Uses the public Microsoft Edge browser API. **Works completely for free and does not require any API keys.**

**Parameters (`voice.tts.cloud.edge`):**
* **`enabled`**: `true` / `false`.
* **`main_voice`**: Main speaking voice (for example, `"ru-RU-SvetlanaNeural"`, `"en-US-AriaNeural"`, or others).
* **`available_voices`**: List of allowed voices (the agent can select a voice when generating speech).
* **`rate`**, **`volume`**, **`pitch`**: Voice modulation settings (format: `"+10%"`, `"-5%"`, `"+5Hz"`).

### ElevenLabs (Paid / Custom)
Uses the premium ElevenLabs service for highly realistic and emotional speech generation.
Requires `ELEVENLABS_API_KEY` specified in the `.env` file.

**Parameters (`voice.tts.cloud.elevenlabs`):**
* **`enabled`**: `true` / `false`.
* **`tts_model`**: Target model (recommended is `"eleven_multilingual_v2"`).
* **`main_voice`**: ID of the primary voice (obtained from your ElevenLabs dashboard).
* **`available_voices`**: List of additional voice IDs the agent can choose from.
* **`stability`** and **`similarity_boost`**: Voice clarity and emotional variance parameters (from `0.0` to `1.0`).