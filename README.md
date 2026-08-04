# JAWL (Just A While Loop)

**JAWL** is an asynchronous framework for creating continuous-loop autonomous AI agents (Event-Driven ReAct Loop).

The project is built around the concept of an autonomous agent operating within an event-driven reasoning and acting cycle. The system gathers context, forms a structured chain of thought, executes actions via available interfaces, and goes to sleep until the next tick or external interruption.

The framework is designed for native execution on the host machine with a flexible access control policy via a built-in Gatekeeper, ensuring safe agent interaction with the OS, file system, and local network without mandatory Docker isolation.

---

## 🏗 Key Architectural Solutions

### 1. Hybrid Vector-Graph RAG
The long-term memory subsystem combines vector semantic search (Qdrant + FastEmbed) and a structured knowledge graph (KuzuDB). Upon receiving incoming events, the orchestrator extracts entities from text, performs cross-resolving across both databases, and generates a summary of facts and causal relationships. This significantly reduces the "amnesia" effect of language models during long-term operation.

### 2. Fractal Tree of Thoughts
Instead of impulsively executing the first generated action, the agent is capable of running an internal scenario simulation. The model builds a recursive tree of macro-strategies and micro-scenarios, accompanying each branch with a Cost-Benefit analysis (lists of pros and risks). This allows evaluating the consequences of decisions before executing them in the real environment.

### 3. Probabilistic Reasoning via Bayesian Hypotheses
The module uses Bayes' formula as a structuring framework for the agent's deductive investigation. In case of errors or uncertainty, the system formulates hypotheses, collects evidence through tools, and mathematically recalculates the confidence level in each hypothesis, protecting against false conclusions via Cromwell's rule.

### 4. Swarm Orchestration
The main agent, acting as an orchestrator, can delegate voluminous and routine tasks to background subagents (`CODER`, `WEB_RESEARCHER`, `ARCHIVIST`, `QA_ENGINEER`, `SYSADMIN`). Subagents operate in isolated `Stateless ReAct` loops on cheaper models, have no access to main memory, and return results as a finalized Markdown report.

### 5. Event-Driven Heartbeat
The agent goes to sleep for a specified interval, but wakes up instantly upon receiving incoming events via the `EventBus`. Depending on the event priority (from `BACKGROUND` to `CRITICAL`), a sleep acceleration multiplier is applied, minimizing the response latency to critical signals.

### 6. Safe Self-Modification
With `OPERATOR` access level, the agent can modify the framework's source code. Changes occur within a deploy session with a Copy-on-Write transactional backup. Before committing, a syntax validator and test suite (`pytest`) are automatically run. If tests fail, the system performs an automatic rollback.

---

## ⚖️ Comparison with Alternatives

| Criterion | JAWL | LangGraph | CrewAI | Letta (MemGPT) | AutoGPT | Hermes Agent | OpenClaw |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Operating Mode** | Infinite Event-Driven loop | Cyclic state graph | Sequential / Hierarchical | LLM OS event cycle | Linear ReAct | **Continuous Event-Driven loop** | **Gateway Event-Driven loop** |
| **Local Memory (Vector + Graph)** | Built-in *(Qdrant + KuzuDB)* | External | Built-in *(ChromaDB + SQLite)* | Built-in *(Vector)* | External | **Built-in** *(Vector + Session Search + SQLite)* | **Built-in** *(Workspace/SQLite)* |
| **OS Access Control** | Built-in *(Gatekeeper 0-3)* | None *(Requires Docker)* | None | None | Restricted *(workspace directory)* | **Restricted** *(containerization / PID limits / OS boundary)* | **Restricted** *(Docker / Allowlists / Pairing)* |
| **Multi-Agent Swarm** | Yes *(Stateless workers)* | Yes | Yes | Yes *(inter-agent calls)* | Restricted | **Yes** *(isolated sub-agents)* | **Yes** *(agent routing via Gateway)* |
| **Autonomous Planning (ToT)** | Yes *(Fractal)* | Manual *(via nodes)* | None | None | None | **None** *(default step auto-decomposition)* | **None** *(linear ReAct execution)* |
| **Self-Modification with Rollback** | Yes *(Deploy Sessions)* | Yes *(Time Travel/Rollback)* | None | None | None | **Yes** *(dynamic auto-creation and skill modification)* | **None** |

---

## 💻 System Requirements

* **Operating System**: Windows 10/11, Linux (Ubuntu 22.04+), macOS.
* **Python Version**: Python 3.11 strictly (*C-extension dependencies are optimized for 3.11*).
* **CPU**: 2+ cores (4+ cores recommended for local FastEmbed vectorizer).
* **RAM**:
  * **Minimum**: 4 GB RAM + **mandatory swap file of at least 2 GB**.
  * **Recommended**: 8 GB RAM or more.
  * *Note*: A swap file is necessary to prevent Out-Of-Memory errors when Qdrant, KuzuDB, and SQLite are active simultaneously.

---

## 🏗 L0 - L3 Architecture

The system is divided into 4 layers in strict adherence to the Single Responsibility Principle (SRP):

* **L0 (State Layer)**: Passive data showcases (MRU caches). Store interface state snapshots (messages, PC metrics, open files) without performing I/O operations.
* **L1 (Databases Layer)**:
  * *SQL (SQLite)*: Tasks (Eisenhower Matrix), personality traits (Traits), tracking entities (Mental States), motivators (Drives), hypotheses (Hypotheses), and tick logs.
  * *Vector DB (Qdrant + FastEmbed)*: Semantic memory (Knowledge and Thoughts).
  * *Graph DB (KuzuDB)*: Knowledge Graph and codebase architecture graph (Code Graph).
* **L2 (Interfaces Layer)**: External interaction plugins (`Host OS`, `Telegram`, `GitHub`, `Email`, `Web Search/Browser/Hooks/RSS`, `Calendar`, `Code Graph`, `Voice`).
* **L3 (Agent Core Layer)**: Compute core (`ReactLoop`, `Heartbeat`, `LLMExecutor` with key rotation, `PromptBuilder`, `ContextBuilder`, `SubconsciousOrchestrator`, `SwarmManager`).

---

## 🛡 Security and Sandbox Limitations

### In-process "sandbox" limitations
The `sandbox_runner.py` and `_sandbox_guard.py` modules represent a **best-effort in-process barrier**, not true OS-level isolation.

**What is intercepted**:
* Path Traversal attempts escaping the `sandbox/` directory via `open()`, `pathlib`, `os.open`, `_io.FileIO`.
* Shell execution attempts via `subprocess.*`, `os.system`, `os.popen`, `os.fork`, `execv*`, `posix_spawn`.
* Direct import of `ctypes.CDLL`.
* Parent process termination attempts via `os.kill`.
* Secret scrubbing from environment variables prior to script execution.

**What the barrier DOES NOT guarantee**:
An in-process guard cannot protect against motivated attacks using C-extensions (Cython), non-trivial `ctypes` calls (loading arbitrary `.so`/`.dll`), direct reading of `/proc/self/mem`, or inline assembly injections.

*Recommendation*: To execute completely untrusted code or code generated by third-party models, run JAWL inside an isolated virtual machine or Docker/Podman container.

---

## 🚀 Installation and Quick Start

### 1. Requirements
Ensure **Python 3.11** is installed on your system.

### 2. Cloning and Setup
```bash
git clone https://github.com/th0r3nt/JAWL.git
cd JAWL
```

Copy the example environment file:
```bash
cp .env.example .env
```
Specify your API keys in `.env` (if missing, the CLI setup wizard will prompt for them on first launch).

### 3. Run
```bash
python jawl.py
```
*The bootstrapper will automatically create a virtual environment (venv), install dependencies, and open the CLI menu.*

### 🐧 Running on Linux VPS
1. Install system dependencies: `sudo apt install -y python3 python3-venv git tmux`
2. Create a Swap file:
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```
3. Run the framework inside a `tmux` session:
   ```bash
   tmux new -s jawl
   python3 jawl.py
   ```

---

## 📜 License
The project is distributed under the [MIT](LICENSE) license.

## Other
The author of this framework (th0r3nt) has a [Telegram channel](t.me/VEGA_and_other_heresy), which often describes additional technical details and other development-related topics.