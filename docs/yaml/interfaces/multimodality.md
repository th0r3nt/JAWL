# Multimodality Configuration (Vision)

The `multimodality` interface allows the agent to "see". It provides skills to upload local images (or screenshots of web pages and the OS) into the language model's context.

## Important Requirement
This interface will function only if your primary LLM model physically supports image processing (for example, `gpt-4o`, `claude-3-5-sonnet`, `gemini-1.5-pro`).

In the `settings.yaml` file, the `llm.is_multimodal` parameter must be set to `true`. If set to `false`, the interface will be forcibly disabled at startup (with a warning in logs) to prevent API crashes.

## How It Works (Base64 Injection)
The agent does not send images via separate requests. When it invokes a viewing skill, the system places a system marker (for example, `[SYSTEM_MARKER_IMAGE_ATTACHED: path/to/image.jpg]`). On the next step of the ReAct cycle, the prompt builder `ReactLoop` locates this marker, reads the image from disk, encodes it to `Base64`, and injects it directly into the request body sent to the LLM along with the current context.