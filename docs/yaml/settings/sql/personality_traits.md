# Acquired Personality Traits (Personality Traits)

The `Personality Traits` module allows the agent to dynamically adapt to the user.

While the primary, rigid personality is defined in static Markdown files (`prompt/personality/SOUL.md`), this SQL module allows the agent to learn rules "on the fly". For example, if the user repeatedly requests code without comments, the agent will autonomously write a trait "Write code concisely," save the application context, and adhere to it in future reasoning.

## Parameters (`system.db.sql.personality_traits`)
* **`enabled`**: `true` / `false`. Enables the traits system.
* **`max_traits`**: Limit on the number of acquired personality traits displayed in the system prompt.