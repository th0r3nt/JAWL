# Mental States

The `Mental States` module is a personal CRM system for tracking external entities (users, other bots, servers, projects).

Unlike dry databases, this module compiles the agent's **"Attitude"** toward targets:
* **Attitude:** The agent can feel `Friendly` toward a particular user or `Suspicious` toward a failing server.
* **Directives:** Individual interaction guidelines (for example, "Never joke with this user" or "Take backup before modifying files on this server").
* **Relations:** The agent remembers interpersonal connections (for example, "User A hates Server B").

These states are constantly injected into the system prompt, causing the agent to organically adapt its tone and decisions based on who it is talking to or which file it is editing.

## Parameters (`system.db.sql.mental_states`)
* **`enabled`**: `true` / `false`.
* **`max_entities`**: Strict limit on the number of tracked entities to protect the context window.