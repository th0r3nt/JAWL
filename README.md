# JAWL (Just A While Loop)

**JAWL** is a standalone framework for building continuous-loop autonomous AI agents.

The project is built around a simple concept: the agent operates within an infinite ReAct (Reasoning and Acting) loop. It continuously gathers context, forms a Chain of Thought, executes useful actions via available interfaces, and goes to sleep until the next tick or an external trigger.

No Docker and no cloud databases. The framework is designed for native cross-platform execution on the host machine with strict access control (Gatekeeper), ensuring the agent can safely interact with the OS, file system, and local networks.

🧠 **Ultimate Hybrid RAG (Vector-Graph RAG):** One of the main distinguishing features of the framework is an innovative memory subsystem that permanently solves the "amnesia" problem of language models over long distances. The system weaves classic vector semantic search (Qdrant + FastEmbed) with strict causal relationships from a knowledge graph (KuzuDB). With every incoming event, the orchestrator extracts entities from the text on the fly, recursively cross-resolves them across both databases, and injects a flawlessly accurate summary of facts and their logical connections into the agent's prompt. This mechanism effectively implements human-like associative memory.

🌳 **Tree of Thoughts (Fractal Strategic Planning):** The second fundamental architectural difference is the presence of a "subconscious" powered by MCTS (Monte Carlo Tree Search) algorithms. Instead of impulsively executing the first idea that comes to mind in a ReAct manner, the agent delegates situation analysis to an independent generator. The system builds a **recursive tree of multi-level simulations**, where macro-strategies branch out into nested micro-scenarios. Every branch undergoes a Cost-Benefit analysis (calculating pros and risks). This allows the agent to "live through" multiple future outcomes in its mind before taking a physical action in reality. An excellent tool for protecting against hallucinations and critical errors.


## 💡 What is this framework perfectly suited for?
Thanks to the L0-L3 architecture, a rich set of interfaces, and the subagent subsystem, JAWL can be used to deploy agents with completely different profiles. Now your agent is not just a lone worker, but a full-fledged Orchestrator capable of managing a swarm of subagents:

* **Lead Tech:** An agent living in your GitHub repositories. Upon noticing a complex Issue, it doesn't waste its expensive context; instead, it delegates the task to a background `CODER` subagent (running on the cheap and fast `Gemini Flash Lite`). The subagent clones the code into a sandbox, debugs it, and makes a Pull Request, while the Main Agent reviews the result, eventually accepts the work, and reports back to you in Telegram.
* **DevOps:** A Watchdog on your VPS. It continuously monitors RAM/CPU consumption and network sockets. If a critical service crashes, the main agent deploys a subagent to parse giant walls of `stderr` logs and search for the error online, while simultaneously applying emergency fixes via shell.
* **OSINT/Deep Research:** You give the agent a complex topic. It decomposes it and spawns a swarm of `WEB_RESEARCHER` subagents. They parallelly scour the internet, read dozens of websites, bypass garbage SEO articles, and bring back ready-made summaries. The main agent consolidates their work, packs the facts into semantic memory (Vector DB), and provides you with a structured Markdown report.
* **Autonomous Self-Improving Agent:** The final stage of the JAWL food chain. You grant the agent `ROOT` access to an isolated OS and `CREATOR` access to the Meta-interface. What happens next?
    * **Psychology and motivators:** The agent notices a growing "Mastery" deficit due to a prolonged absence of your commands. To satisfy this need, it decides to write a new integration for itself (e.g., a Crypto Exchange API or Discord).
    * **Introspection via Code Graph:** It unleashes an AST-parser on its own JAWL source code to calculate the "Blast Radius" — exactly which framework modules it needs to touch and which tests to update.
    * **Multi-level Tree of Thoughts simulation:** Before writing the code, its subconscious generates a fractal tree of strategies. The agent runs 3 macro-variants of the architecture "in its mind", weighs the pros and risks of each micro-scenario, and simulates events to ensure it won't break its own code.
    * **Swarm Orchestration:** The Orchestrator doesn't dirty its hands with routine. It simultaneously spawns a `WEB_RESEARCHER` subagent to parse API documentation from websites and sends a `CODER` subagent to write a Python script in the sandbox. They are monitored by a `QA_ENGINEER`, who runs hardcore `pytest` sessions until the code is flawless.
    * **Safe self-modification:** The self-preservation mechanism is enabled. If a subagent breaks the syntax, the framework won't die; it will automatically rollback to a working version.
    * **Runtime Evolution:** As soon as the tests are green, the Orchestrator injects the new script into its brain on the fly, displays a crypto price chart on a self-written `Custom Dashboard` right in the system prompt, and spins up a `Webhook` server to receive live quotes.
    * **Result:** You come back with your coffee, and your agent has independently learned to trade on the exchange, updated its own source code, and sent you a report about it in Telegram.


## 🏗 L0 - L3 Architecture
The project is divided into 4 areas of responsibility:

* **L0 (State):** Passive data showcases (MRU-caches). They store state snapshots (latest messages, PC metrics, browser history, timers). They save tokens because the agent doesn't need to spend API calls just to "look around".

* **L1 (Databases):** Local memory layer.
  * *SQL (SQLite):* Long-term Tasks, acquired character Traits, entity tracking and Theory of Mind (Mental States), motivation (Drives), deductive Hypotheses, and complete agent tick logs.
  * *Vector (Qdrant + FastEmbed):* Semantic memory. Runs locally on CPU. Divided into `knowledge` (facts from the outside world) and `thoughts` (internal reflection) collections.
  * *Graph (KuzuDB):* Knowledge Graph. Stores nodes and builds strict causal links for perfect semantic resolving and prevention of long-distance amnesia.

* **L2 (Interfaces):** Windows to the outside world.
  * *Host OS:* File, process, network, and GUI (clipboard, notifications) management on the host machine. Built-in `sandbox/` with a protected API for scripts.
  * *Telegram:* Support for User-API (`Telethon`) and Bot-API (`Aiogram`).
  * *GitHub:* REST API (Issues, PRs, trend search) + Local Git (the agent can clone repos into the sandbox, write code, and push/commit on its own behalf).
  * *Email:* Reading, sending, and sorting mail (IMAP/SMTP) with automatic server detection.
  * *Web Search, HTTP, Browser & Webhooks*: Search, web scraping, a headless browser based on Playwright, and **a custom HTTP server for receiving incoming webhooks**.
  * *Calendar:* Time management, setting interval and one-time wake-up triggers.
  * *Multimodality:* Vision. The agent can "look" at local images or browser screenshots if the main LLM supports it.
  * *Meta:* Interface for changing the agent's configuration at runtime.
  * *Code Graph:* An Agentic Introspection tool. Parses the AST of Python projects, builds a dependency/relationship graph of files, functions, and classes, allowing the agent to semantically search code and calculate the Blast Radius during refactoring. The agent can find a required piece of code simply by describing its meaning (e.g., *"where are the logs saved?"*).
  * *Voice (TTS/STT):* The agent can synthesize speech (via flexible connectors to ElevenLabs TTS, Edge TTS, or local solutions) and transcribe audio files (OpenAI Whisper, Vosk, local solutions), turning into a full-fledged voice assistant.

* **L3 (Agent Core):** The brain of the system. Contains the `ReactLoop`, context assemblers, automatic RAG, `Pydantic Guard Layer`, and `Heartbeat` (event-driven pulse). The LLM can be either cloud-based or local.

### More details about the architecture: [architecture.md](docs/architecture.md).


## 🐝 Swarm (Multi-Agent Subsystem)
JAWL supports scaling via delegation. The Main Agent (Orchestrator) can spawn background **subagents** for the parallel execution of resource-intensive tasks.

### Why is this needed?
* **Saving tokens and money:** The Main Agent (e.g., the expensive `Claude Opus`) doesn't need to waste its context scrolling through dozens of websites looking for the right information. It delegates this task to a subagent running on a fast and cheap model (e.g., `Gemini Flash Lite`) and receives only the finalized summary.
* **Isolation:** Subagents operate in a lightweight `Stateless ReAct` loop. They don't see the agent's main memory, its chats, or the system log.
* **Parallelism:** The Main Agent can launch several subagents at once and peacefully go to sleep. The subagents will work in the background (each in its own `asyncio` task) and send reports when they finish. The `SUBAGENT_TASK_COMPLETED` event will instantly wake up the Orchestrator to accept the work.

### Available Roles (RBAC)
Each role has its own narrow system prompt and strictly limited access to interfaces:
* 💻 **CODER**: Access to the isolated sandbox (within `sandbox/`), safe script execution, and local Git (clone, checkout, commit, push).
* 🕵️ **WEB RESEARCHER**: Access to DuckDuckGo, Tavily, Jina, Trafilatura, and a powerful `DeepResearch` skill (parallel searching and reading of up to 20 unique web pages at a time).
* 🗄️ **ARCHIVIST**: Access to long-term memory (Vector DB). Responsible for background revision, finding duplicates, compressing facts, and removing informational noise for flawless RAG performance.
* 🛡️ **QA ENGINEER**: Access to the file system, code execution, and network. Writes hardcore `pytest` tests instead of features, runs them through multiple iterations, and hunts for edge cases.

### Recommended reading: [Subagents Subsystem Documentation](docs/subagents.md).


## ⚙️ Key Features

* **Total Access Control:** Agent permissions are managed in a few clicks via the CLI menu. You configure in detail what the agent has access to: from enabling specific interfaces (Telegram, GitHub) to the depth of intervention. Host OS privileges range from a locked `SANDBOX` to full `ROOT` access. Meta-privileges for configuring the system itself range from a safe minimum (`SAFE`) to self-modification rights (`CREATOR`). Automatic protection of `.env` files is built in at the code level.
* **Fractal Tree of Thoughts Generation:** You can configure the geometry of the simulation tree (e.g., 3 macro-strategies, each with 2 nested scenarios and 2 event simulations). The model will generate this tree, weigh all the pros and cons for each node, and only then will the main agent choose the ideal path. Supports automatic generation every N steps, manual triggering (`deep_think`) by the agent, or a hybrid mode.
* **Background Subconscious:** The agent is freed from the need to spend expensive time (and powerful model tokens) on routine database management. A dedicated subsystem running on fast and cheap LLMs quietly wakes up on a schedule in the background. It performs memory consolidation (moving important facts from temporary logs to long-term Vector DB), behavior reflection, and information hygiene (deleting duplicates and trash).
* **Probabilistic Thinking via Bayes' Theorem:** When faced with a system error or uncertainty, the agent formulates hypotheses, collects facts (logs, API responses) through tools, and mathematically recalculates its confidence in each hypothesis using Bayes' theorem.
* **Code Graph:** The agent can algorithmically index any codebase (including JAWL's own architecture), turning it into a vector-graph map. Skills for semantic search and Trace Dependencies allow it to work with projects of any size, navigating the code like an IDE without overflowing the context window.
* **Safe Self-Modification:** If the agent gains `OPERATOR` level access (rights to modify JAWL's source code), the system protects itself from fatal breakdowns. To change the architecture, the agent must open a *Deploy Session*. The system automatically runs tests and syntax checks; if an error occurs, an automatic Rollback is triggered.
* **Powerful Test Base:** The framework's architecture is covered by reliable auto-tests (*580+ tests*). This includes database integration tests and **End-to-End (E2E) testing**, guaranteeing the stability of the code and interfaces.
* **Psychology and Motivators**: The agent possesses a built-in mathematical model of needs, translated into semantic "self-awareness" (a 7-step scale of states ranging from "Intellectual Satiety" to "Acute Deprivation"). During a long absence of commands, growing discomfort (a deficit in Curiosity or Order) will force the agent to proactively look for work: refactor code, surf news relevant to its task, or initiate a dialogue. This saves the system from the "dead idle" problem.
* **Mental States & Theory of Mind:** The system not only remembers facts about people and servers but also forms its *attitude* towards them. The built-in Epistemic State model allows the agent to track the level of expertise and knowledge of the interlocutor (what they know and what they don't) and dynamically calibrate its attitude/responses based on the assessment of their knowledge.
* **Event-Driven Heartbeat:** The agent sleeps between ticks but wakes up instantly upon receiving incoming events via the `EventBus`. The remaining sleep time is dynamically reduced depending on the event level (CRITICAL, HIGH, MEDIUM, LOW, BACKGROUND).
* **Excellent Documentation:** The framework is provided with comprehensive documentation (`docs/` folder) and user-friendly reference templates.


## 🎭 Personality Customization
JAWL allows you to configure the agent's character and behavior with extreme flexibility. In the `src/l3_agent/prompt/personality/` directory, you'll find the base Markdown files with the system prompt (`SOUL.md` and `EXAMPLES_OF_STYLE.md`).

The `PromptBuilder` **automatically concatenates all `.md` files** from this folder before sending the context. This means you are not limited to the current files. You can create as many custom documents as you want to describe the agent. For example:
* `COMMUNICATION_STYLE.md` - for strict control over the tone and format of responses.
* `LORE.md` - to load the backstory or rules of your company.
* `TABOOS.md` - to describe what the agent is strictly forbidden to say.

*On the first run, the system will automatically create a base personality from the `.example.md` files if you haven't created them yourself.*


## 🚀 Installation and Launch

*Requirements: Make sure you have Python 3.11 installed and added to PATH.* 
*Important: some AI libraries in JAWL do not work well on Python 3.12+ and above.*

1. **Cloning:**
   ```bash
   git clone https://github.com/th0r3nt/JAWL.git
   cd JAWL
   ```

2. **Configuration:**
   * Copy `.env.example` to `.env` and add your LLM API keys (and interface tokens, if you plan to use them). However, if you forget, the CLI installer will ask for the key on the first run.
   * If necessary, edit `config/settings.yaml` (model settings, DB, limits) and `config/interfaces.yaml` (modules and access levels).

3. **One-Command Magic:**
   ```bash
   python jawl.py
   ```
   *The script will automatically deploy a virtual environment, download the libraries, and open an interactive setup and management menu for the agent.*


> **🐧 Instructions for clean Linux (Ubuntu/Debian VPS):**
> 1. Install system dependencies: `sudo apt install -y python3 python3-venv git tmux`
> 2. You must add a Swap file (minimum 2GB) so the system doesn't kill the vector DB during initialization.
> 3. Run the framework inside `tmux` so the agent continues to work after you close the SSH session: 
>    `tmux new -s jawl` -> `python3 jawl.py`


## 📜 Development Principles
* **KISS & DRY:** The code is written so it can be read without a dictionary.
* **No overengineering:** Abstractions are introduced only where they solve a real problem. The OOP Inquisition won't condemn us for this.
* **SOLID:** Strict layer isolation. The brain (L3) doesn't know how the database (L1) works; it communicates with it only through clearly defined interfaces.


## 🛡️ Security and Disclaimer
JAWL is a framework that (under certain settings) is capable of downloading files from the network, writing code, and executing shell commands. "With great power comes great responsibility."

* **The framework is provided "As Is".** The author bears no responsibility for any destructive actions of the agent, data loss, or token leakage. You run the project at your own risk.
* **Isolation:** By default, the agent runs in `SANDBOX` mode (access only to the `sandbox/` folder). **It is highly recommended NOT to enable** `ROOT` access level (3) on your main working machine. If you want to give the agent full OS access, it is recommended to use a virtual machine (VMBox) or an isolated Linux container without `sudo`.
* **In-process "sandbox" limitations:** `sandbox_runner.py` / `rpc_wrapper.py` is a **best-effort in-process barrier**, not true isolation. It is capable of blocking trivial vectors (`subprocess`, `os.system`, standard `open()`, `pathlib`, `os.open`, `_io.FileIO`, `os.fork`/`execv*`/`posix_spawn`, `ctypes.CDLL("libc.*")`, `importlib.reload` of protected modules, `os.kill` of the parent process) and scrubs environment variables with secrets. **It is NOT capable** of protecting against a motivated attacker: any Cython/C-extension, non-trivial use of `ctypes` (loading an arbitrary `.so` bypassing `libc`), `mmap`, or calling a syscall via inline-assembly in CPython extensions will bypass the in-process guard. For an agent executing untrusted Python code (including LLM-generated code), use external isolation: seccomp / Docker / Podman / a separate namespace-user / a full VM.
* **Secrets and .env:** Never add your main, personal, or corporate tokens to `.env`. Recommended:
  * If the GitHub interface is enabled - A separate GitHub PAT (Personal Access Token) with the minimum required permissions.
  * If the Email interface is enabled - A specially dedicated mailbox.
  * LLM keys with strictly set financial limits (so that if the agent accidentally goes into an infinite loop due to an error, it doesn't burn through your credit card).


## 📜 License
The project is distributed under the [MIT](LICENSE) license.

---

*Designed and written by [th0r3nt](https://t.me/VEGA_and_other_heresy).*
No abstract factories were harmed in the making of this framework (they simply weren't allowed in).