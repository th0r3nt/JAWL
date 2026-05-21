# LLM Configuration (`llm`)

The `llm` block in `settings.yaml` manages the interaction with language models.

* **`main_model`**: Model identifier (e.g., `gpt-4o`, `claude-3-5-sonnet`) used by the main Orchestrator agent.
* **`available_models`**: A list of models available to the agent. If the Meta interface is enabled (SAFE level or higher), the agent can switch its active model on the fly, selecting from this list for specific tasks.
* **`is_multimodal`**: `true` / `false`. Set to `true` only if your model physically supports image processing. This enables passing screenshots into the prompt.
* **`temperature`**: Creativity factor from 0.0 (highly deterministic) to 1.0+ (highly creative).
* **`max_react_steps`**: Hard limit on the number of "Thought -> Tool Call -> Result" iterations per single wakeup step. If the agent gets stuck in a loop or encounters an unresolvable error, the system will forcibly put it to sleep after reaching this limit to protect your API balance.

## Connecting Local Models (Ollama, vLLM, LM Studio)

JAWL fully supports local models out of the box, provided they expose an OpenAI-compatible REST API (which almost all popular solutions do).

**How to configure:**
1. Start your local model (e.g., `ollama run model_name`).
2. In your `.env` file, specify the local host address in the `LLM_API_URL` parameter (for example, `http://127.0.0.1:11434/v1/` for Ollama or `http://127.0.0.1:1234/v1/` for LM Studio).
3. Leave the `LLM_API_KEY_1` field in `.env` **completely empty**. The system will automatically use a placeholder and won't require authorization.
4. In `settings.yaml`, specify the exact name of your local model in the `llm` -> `main_model` parameter.

*Note: You can use an expensive cloud model for the main Orchestrator agent while delegating routine subagent tasks to a cheap or free local model. To do so, specify the local endpoint in the `SUB_LLM_API_URL` environment variables in your `.env` file.*