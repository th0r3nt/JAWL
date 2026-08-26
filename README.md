
# JAWL (Just A While Loop)

**JAWL** is an asynchronous framework for creating continuous-loop autonomous AI agents (Event-Driven ReAct Loop) featuring a full-fledged local Web Management Cockpit.

The project is built around the concept of an autonomous agent operating within an event-driven reasoning and acting cycle. The system gathers context, forms a structured chain of thought, executes actions via available interfaces, and goes to sleep until the next tick or external interruption.

The framework is designed for native execution on the host machine with a flexible access control policy via a built-in Gatekeeper, ensuring safe agent interaction with the OS, file system, and local network without mandatory Docker isolation.

Russian README [is here](https://github.com/th0r3nt/JAWL/blob/main/README_RU.md).

---

## 🖥 Web Management Cockpit

Starting with version `v0.17.0-stable`, JAWL includes a local web cockpit dashboard (available by default at `http://127.0.0.1:8770/`):

* **Live Heartbeat Pulse:** Real-time cardiogram of agent wakeups, sleep/wake cycles, ReAct steps, and live activity visualization.
* **Visual Parameter Editor:** Live configuration for LLM models, API key pools, temperature, hybrid RAG memory, context limits, Swarm subagents, and subconscious routines without manual YAML parsing.
* **Interface Integrations:** Granular control over OS Access Levels (0-3), Telegram (Telethon/Aiogram), GitHub, Email, Web Browser (Playwright), Voice (STT/TTS), Webhooks, and RSS.
* **Operator Chat Console:** Direct, bidirectional operator chat triggering immediate wakeups (CRITICAL events).
* **Psychological Drives Radar:** Real-time deficit meters tracking internal needs (Curiosity, Social, Mastery, Custom).
* **Database & Memory Inspector:** Inspection and safe wiping tools for SQL, vector collections (Qdrant), embedding models cache, knowledge graphs (KuzuDB), and sandbox data.
* **Live Log Streaming:** SSE-driven streaming of `main.log` with real-time severity level filtering.

---

## 🏗 Key Architectural Solutions

### 1. Hybrid Vector-Graph RAG
The long-term memory subsystem combines vector semantic search (Qdrant + FastEmbed) and a structured knowledge graph (KuzuDB). Upon receiving incoming events, the orchestrator extracts entities from text, performs cross-resolving across both databases, and generates a summary of facts and causal relationships.

### 2. Fractal Tree of Thoughts (ToT)
Instead of impulsively executing the first generated action, the agent is capable of running an internal scenario simulation. The model builds a recursive tree of macro-strategies and micro-scenarios, accompanying each branch with a Cost-Benefit analysis (lists of pros and risks).

### 3. Probabilistic Reasoning via Bayesian Hypotheses
The module uses Bayes' formula as a structuring framework for the agent's deductive investigation. In case of errors or uncertainty, the system formulates hypotheses, collects evidence through tools, and mathematically recalculates the confidence level in each hypothesis.

### 4. Swarm Orchestration
The main agent, acting as an orchestrator, can delegate voluminous and routine tasks to background subagents (`CODER`, `WEB_RESEARCHER`, `ARCHIVIST`, `QA_ENGINEER`, `SYSADMIN`). Subagents operate in isolated `Stateless ReAct` loops on cheaper models and return results as finalized Markdown reports.

### 5. Event-Driven Heartbeat
The agent goes to sleep for a specified interval, but wakes up instantly upon receiving incoming events via the `EventBus`. Sleep acceleration multipliers minimize response latency to critical incoming signals.

### 6. Safe Self-Modification (Deploy Sessions)
With `OPERATOR` access level, the agent can modify the framework's source code. Changes occur within a deploy session with a Copy-on-Write transactional backup, running automated syntax checks and `pytest` test suites with rollback safety.

---

## ⚖️ Comparison with Alternatives

| Criterion | JAWL | LangGraph | CrewAI | Letta (MemGPT) | AutoGPT | Hermes Agent | OpenClaw |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Operating Mode** | Infinite Event-Driven loop | Cyclic state graph | Sequential / Hierarchical | LLM OS event cycle | Linear ReAct | Continuous Event-Driven loop | Gateway Event-Driven loop |
| **Management UI** | **Web Cockpit + CLI Terminal** | LangSmith (Cloud) | CLI / UI | REST API / Web | Web UI | CLI | Gateway / Web UI |
| **Local Memory (Vector + Graph)** | Built-in *(Qdrant + KuzuDB)* | External | Built-in *(ChromaDB + SQLite)* | Built-in *(Vector)* | External | Built-in *(Vector + SQLite)* | Built-in *(Workspace/SQLite)* |
| **OS Access Control** | Built-in *(Gatekeeper 0-3)* | None *(Requires Docker)* | None | None | Restricted *(workspace)* | Restricted *(OS boundary)* | Restricted *(Docker/Pairing)* |
| **Multi-Agent Swarm** | Yes *(Stateless workers)* | Yes | Yes | Yes *(inter-agent calls)* | Restricted | Yes *(isolated sub-agents)* | Yes *(agent routing via Gateway)* |
| **Autonomous Planning (ToT)** | Yes *(Fractal)* | Manual *(via nodes)* | None | None | None | None | None |
| **Self-Modification with Rollback** | Yes *(Deploy Sessions)* | Yes *(Time Travel/Rollback)* | None | None | None | Yes *(dynamic skills)* | None |

---

## 💻 System Requirements

* **Operating System**: Windows 10/11, Linux (Ubuntu 22.04+), macOS.
* **Python Version**: Python 3.11 strictly (*C-extension dependencies are optimized for 3.11*).
* **CPU**: 2+ cores (4+ cores recommended for local FastEmbed vectorizer).
* **RAM**:
  * **Minimum**: 4 GB RAM + **mandatory swap file of at least 2 GB**.
  * **Recommended**: 8 GB RAM or more.

---

## 🚀 Installation and Quick Start

### 1. Cloning
```bash
git clone https://github.com/th0r3nt/JAWL.git
cd JAWL
```

### 2. Launch Web Cockpit (Recommended)
On Windows, simply run `start.bat`.

Or run via terminal:
```bash
python -m src.web
```
*The launcher will automatically configure missing files from templates, start the local server at `http://127.0.0.1:8770/`, and open your default browser.*

### 3. Launch CLI Terminal Menu (Headless)
If you are running in a headless environment:
```bash
python jawl.py
```
*The bootstrapper will create a virtual environment (venv), install dependencies, and launch the terminal UI.*

### 🐧 Running on Linux VPS
1. Install system dependencies: `sudo apt install -y python3 python3-venv git tmux`
2. Create a Swap file:
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```
3. Run the Web Cockpit for remote access:
   ```bash
   python -m src.web --host 0.0.0.0 --port 8770 --token your_secret_token --no-browser
   ```

---

## 📜 License
The project is distributed under the [MIT](LICENSE) license.

## 👥 Authors & Contributors

* **[th0r3nt](https://t.me/th0r3nt)** — Creator & Lead System Architect of JAWL.
* **[IceSondu](https://github.com/IceSondu)**— Web control panel developer and designer.

* 
## Other
The author of this framework (th0r3nt) has a [Telegram channel](https://t.me/VEGA_and_other_heresy), which often describes technical details and development updates.
