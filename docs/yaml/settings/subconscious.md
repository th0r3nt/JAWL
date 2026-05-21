# Subconscious Configuration (Subconscious)

The `subconscious` module allows the Main Agent (Orchestrator) to delegate routine database maintenance tasks to background micro-processes.

While the Orchestrator "reasons" in real-time, the Subconscious operates in the background: it wakes up on a schedule based on tick counts, analyzes raw database dumps, and tidies up, without blocking the main reasoning loop.

It is highly recommended to use **cheap and fast models** for these background tasks.

## Behavior Patterns

The Subconscious is divided into 3 independent patterns, each having its own tick threshold counter and system prompt instructions.

### 1. Consolidation
- **Goal:** Transfer of facts from temporary episodic memory (agent's actions history logs) to long-term memory (Vector DB).
- **How it works:** Reads the agent's last N actions. If the agent learned something important (for example, a credential, a server fact, or a new technology), the Subconscious silently calls the `save_knowledge` skill to preserve it.

### 2. Reflection
- **Goal:** Relationship audit and behavioral adaptation.
- **How it works:** If the agent regularly interacts with a specific user or encounters crashes on a particular system, the Subconscious updates the entity's card in the Mental States database or adds a new acquired Personality Trait.

### 3. Forgetting (Information Hygiene)
- **Goal:** Purging databases of redundant or corrupted data.
- **How it works:** Scans Vector and Graph DB dumps. If it finds parsing errors, obsolete temporary records, or duplicate entries, it purges them to maintain high semantic density for future RAG lookups.

## Parameters (`system.subconscious`)

* **`enabled`**: `true` / `false`. Global switch for the subconscious module.
* **`llm_model`**: Model identifier for background processes (specify the cheapest available model).
* **`patterns`**: Individual configurations for each pattern.
  * **`enabled`**: `true` / `false`. Enables or disables the specific pattern.
  * **`activation_limit_ticks`**: Execution frequency. For example, `30` means this pattern will run once every 30 main agent ticks. It is recommended to use `30` for Consolidation and `90` or higher for Forgetting.