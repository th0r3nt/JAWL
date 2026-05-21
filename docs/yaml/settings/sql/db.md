# Relational Memory Limits (`system.db.sql`)

SQL memory (SQLite) acts as a fast-access cache integrated directly into the agent's system prompt (unlike RAG, where a search query is required).

To prevent the system prompt from being overloaded and triggering a `Maximum Context Length Exceeded` error, `settings.yaml` provides strict row limits on the number of concurrent records stored.

The entire SQL memory is divided into 6 cognitive subsystems. Detailed guides on their operations and configurations are located in the corresponding files:

1. [Tasks (Eisenhower Matrix)](tasks.md) — Long-term planning and delegation.
2. [Mental States (Subjects/Objects)](mental_states.md) — Social radar, statuses, and relations.
3. [Drives (Psychology)](drives.md) — Internal motivation and proactivity.
4. [Notes (Working Memory)](notes.md) — "Sticker-notes" for temporary data.
5. [Personality Traits](personality_traits.md) — Dynamic character adaptation.
6. [Hypotheses (Bayesian Probabilistic Reasoning)](hypotheses.md) — Deductive investigations (Bayes' Theorem).