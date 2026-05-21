# 🧠 Memory and Motivation: Cognitive Architecture

Unlike classic chat bots that lose the thread of conversation when the context window overflows, JAWL agents rely on a hybrid memory system (L1 Databases) and a mathematically calculated model of motivation (Drives).

---

## 🗄️ Memory Subsystems (L1)

The agent's memory is physically and logically divided into two paradigms: **SQL** (structured) and **Vector DB** (semantic).

### 1. SQL: Structured Memory (SQLite)
Used for data requiring precise querying, state updates, and deletion.
* **Tasks:** Planning module. The agent decomposes complex goals into subtasks with progress tracking (0-100%) and blocking dependencies.
* **Personality Traits:** The agent is capable of adaptation. If it notices that the user prefers a certain communication format, it adds a new character trait to itself, which will remain in its system prompt forever.
* **Mental States:** The agent's address book and CRM. Here, data about people, projects, or servers is stored. The agent updates their statuses (for example, "Server DB-1: Down, awaiting reboot").
* **Ticks (Actions Log):** A strict audit of each of the agent's steps (Thoughts -> Action -> Result). Used for debugging and reflection.

### 2. Vector DB: Semantic Memory (FastEmbed + Qdrant)
Used for unstructured blocks of text. Vectors are generated locally on the CPU, saving money and protecting privacy. Divided into two collections:
* **Knowledge:** Facts from the external world. Documentation, read articles, log fragments.
* **Thoughts:** The agent's own logical conclusions and reflections.

**Auto-RAG Mechanism:** On each step of the agent's reasoning, `ContextBuilder` extracts key words from the wakeup trigger (for example, active thoughts or incoming message text) and performs a hidden semantic search across the Vector DB. Retrieved memories are automatically injected into the prompt in the `RELEVANT INFORMATION` block.

---

## 🔥 Drives (Motivators)

One of the main problems of autonomous agents is idling: if no incoming commands are received, they remain inactive. JAWL implements the concept of "Drives" (Motivators), which emulates internal needs.

### How it works:
Each drive has a **deficit metric (0-100%)** and a **decay rate (decay_rate)**.
For example, the fundamental drive `Curiosity` can increase its deficit by 10% every hour.

1. If nobody writes to the agent and nothing happens, the Curiosity deficit will gradually reach a critical threshold (for example, 90/100).
2. On a scheduled Heartbeat tick, the agent will see on its dashboard that the need for information has become critical.
3. This will trigger proactive actions: the agent can go and search for new articles via Web Search, analyze trends on GitHub, or refactor its code if it notices bugs. Again, the direction of study is validated by the agent's personality and active tasks.
4. After a useful action, the agent invokes the `satisfy_drive` skill, reducing the deficit and writing a reflection on how this action resolved the need.

In addition to fundamental drives, the system allows the agent (via SQL skills) to **create custom drives** for specific user tasks (for example, "Server Security Paranoia"). This allows gradually building a unique personality for your agent based on its interactions.