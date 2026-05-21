# Context Management (`context_depth`)

Each completed action of the agent is logged in the database as a "Tick" (Thoughts -> Tool Call -> Result). The agent sees its history in the system prompt, which helps it maintain coherence.

To extremely save tokens and maintain LLM focus, the history is structured into a 3-Tier Episodic Memory architecture:

1. **High Ticks (`high_ticks`)**: The freshest reasoning steps. Transmitted to the agent with maximum details (including full tool outputs and JSON parameters).
2. **Medium Ticks (`medium_ticks`)**: Intermediate steps. Long outputs and parameters are truncated (`_short_max_chars`) to keep the prompt clean but preserve awareness of what was executed.
3. **Low Ticks (`low_ticks`)**: Older steps. Physical actions and results are **completely hidden**. The agent only sees its past thoughts (`thoughts`), allowing it to remember the train of thought without wasting hundreds of thousands of tokens on old system I/O logs.

**Example (`high: 3`, `medium: 7`, `low: 20`)**:
A total of 30 past steps are injected. The last 3 are fully verbose, the preceding 7 are compressed, and the oldest 20 are represented as a clean, continuous inner monologue.

### Truncation Limits
- **`tick_action_max_chars` / `tick_result_max_chars`**: Character limit ceilings for fresh (HIGH) steps.
- **`tick_thoughts_short_max_chars` / `tick_action_short_max_chars` / `tick_result_short_max_chars`**: Rigid character limit constraints for compressed (MEDIUM and LOW) steps.