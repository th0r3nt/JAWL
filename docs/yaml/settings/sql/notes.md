# Working Memory (Working Memory / Notes)

The `Notes` module provides the agent with working memory, operating on the principle of "sticky notes on a monitor."

Unlike the RAG mechanism (Vector DB) which works like a library (you must query it to recall), Notes are always in the agent's peripheral vision - they are displayed in the system prompt on every execution step.

## Why Is This Needed?
This is critically important to maintain coherence across long ReAct reasoning cycles. The agent can use notes to store:
- IP addresses and ports it is currently interacting with.
- Internal To-Do lists.
- Intermediate computation results.
- Temporary IDs of messages, topics, or tasks.
- Active hypotheses and algorithms, so they are not forgotten if the cycle gets distracted by an external event.

## Compression Mechanism
To prevent the agent from burning the context window by storing a giant 10k character text block in a note, the system automatically truncates long notes in the system prompt. The agent will see the beginning of the note, but must explicitly call `list_all_notes` to read the full text.

## Parameters (`system.db.sql.notes`)
* **`enabled`**: `true` / `false`. Enables or disables the working memory notes.
* **`max_notes`**: Maximum number of concurrent notes (memory slots). If reached, the agent must proactively delete old notes before creating new ones.