# 🏗 JAWL Architecture: From L0 to L3

The JAWL framework is designed with strict adherence to SOLID principles. The core concept of the system is the isolation of layers. The agent's "brain" (LLM) should know nothing about how HTTP requests or SQL tables are implemented. It communicates with the outside world exclusively through a standardized interface of skills (Skills) and context (State).

The system is divided into 4 conceptual layers and unified by a single event bus.

---

## 🟢 L0: State (State Layer)
**Essence:** Passive agent dashboard.
**Directory:** `src/l0_state/agent/` (for the agent).

This layer stores MRU (Most Recently Used) caches and current state snapshots of interfaces (for example, the last 10 messages from Telegram, current open files in the sandbox, CPU load). 
To maintain the High Cohesion principle, the states of interfaces are stored within their own packages, while the state of the core itself resides in `l0_state`.

**Strict L0 Rule:** State classes are prohibited from executing I/O operations, network requests, or heavy computations. They only store data.

When the agent wakes up, the context builder instantly gathers data from L0 and compiles the system prompt. This eliminates the need for the agent to waste tokens (and time) on function calls like `get_system_status()` or `read_chat()`.

## 🟡 L1: Databases (Memory Layer)
**Essence:** Local data storage.
**Directory:** `src/l1_databases/`

The layer is divided into two parts, providing the agent with long-term memory:
1. **SQL (SQLite):** Cognitive and structural memory. Stores exact relational data: current tasks (Tasks), acquired character traits (Traits), tracking of external entities (Mental States), and history of its own actions (Ticks).
2. **Vector DB (Qdrant + FastEmbed):** Semantic memory. Runs locally on the CPU. Stores fragments of knowledge (Knowledge) and logical conclusions (Thoughts). Allows the agent to automatically recall relevant information thanks to the built-in RAG mechanism.

## 🟠 L2: Interfaces (Interfaces Layer)
**Essence:** Sensory organs and hands of the agent (Windows to the outside world).
**Directory:** `src/l2_interfaces/`

This is where the business logic of interacting with external APIs (Telegram, GitHub, Email, Host OS) is implemented. Each interface is assembled according to a unified pattern of 5 components and is a completely self-sufficient module:
* `state.py` - Interface dashboard (L0).
* `plugin.py` - Plugin entry point (inherits from BaseInterface). Handles dependency injection (DI) into the container.
* `client.py` - Connection, token management, and binding to L0 State.
* `events.py` - Background pollers and listeners (the agent's ears). They wait for external triggers and dispatch them to the EventBus.
* `skills/` - Decorated methods (`@skill()`) that turn into JSON Schema for LLM invocation (the agent's hands).

Assembly occurs dynamically (Plugin Discovery). The core scans the folder, finds plugins, and initializes them if they are enabled in `interfaces.yaml`.

## 🔴 L3: Agent Core (Core Layer)
**Essence:** Central nervous system and Brain.
**Directory:** `src/l3_agent/`

The layer, independent of specific API implementations. Contains:
* **LLM Executor & Key Rotator:** Integration with neural network APIs, handling Rate Limits (429), and automatic key rotation.
* **Prompt Builder:** Compiling the agent's personality from separate `.md` files.
* **Context Builder & RAG:** Compiling dynamic context from L0 State and the Vector Database.
* **React Loop:** Main `Reasoning and Acting` cycle. Parsing model responses, protecting against hallucinations via the `Pydantic Guard Layer`, and executing requested skills.
* **Heartbeat:** Time orchestrator. Calculates how long the agent should sleep until the next scheduled tick and is capable of urgently waking up the cycle upon receiving critical events from the EventBus.

---

## ⚡ EventBus (Event Bus)
The system has an Event-Driven architecture. Interfaces (L2) do not invoke the agent (L3) directly. Instead, background pollers publish events to the `EventBus` (for example, `EMAIL_INCOMING`).

`Heartbeat` listens to these events. Each event has its own level of importance (from `BACKGROUND` to `CRITICAL`). Depending on the level, Heartbeat applies an acceleration multiplier (`EventAccelerationConfig`) and reduces the agent's sleep time. If the event is critical, the agent wakes up immediately, interrupting its current sleep.