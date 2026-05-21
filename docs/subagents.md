# 🐝 Swarm: Subagents System (Multi-Agent Subsystem)

In JAWL v0.10.0, the **Swarm** subsystem was introduced. It allows the main agent (Orchestrator) to delegate voluminous, resource-heavy, or routine tasks to background subagents (Workers).

Main concept: **Subagents are isolated, blind workers.** They do not have access to your chat history, long-term memory (SQL/Vector), or general context. They only receive a specific task and a set of authorized tools, perform the work, and return a strict Markdown report to the main agent.

---

## 🛠 Part 1. For Users (How to Enable and Use)

Delegating solves two major problems: **saving expensive tokens** and **parallelism**. Instead of forcing an expensive model like `Claude Opus` to scroll through 20 websites, it delegates this task to a background `CODER` or `WEB_RESEARCHER` subagent (running on the cheap and fast `Gemini Flash Lite`), which will do all the dirty work in the background and return a finalized summary.

### 1. Enabling and Configuration
Open `config/settings.yaml` and locate the `swarm` block:

```yaml
  swarm:
    enabled: true
    subagent_model: gemini-3.5-flash # Great model for workers
    max_concurrent_workers: 3 
```

* **subagent_model**: It is highly recommended to use cheap, fast models with large context windows.
* **max_concurrent_workers**: Protection against Rate Limits. If the agent decides to launch 10 subagents at once for parsing, your API provider will ban you (HTTP 429). The semaphore limits parallel execution (others will queue).

### 2. Available Roles
By default, the following specialists are available out of the box:
* 💻 **CODER (Software Engineer)**: Has access to the isolated `sandbox/` folder. Can read files, write scripts, execute them, and work with local Git (clone, commit, push). Great for refactoring and debugging.
* 🕵️ **WEB RESEARCHER (OSINT Analyst)**: Has access to search engines and web page readers. Owns a powerful `DeepResearch` skill (can search and read up to 20 unique websites concurrently in a single call). Great for fact-checking and gathering lore.
* 🗄️ **ARCHIVIST**: Has access to long-term memory (Vector DB). Responsible for background database revision, locating duplicates, compressing facts, and removing informational noise for perfect RAG performance.
* 🛡️ **QA ENGINEER**: Has access to the file system, code execution, and network. Writes rigorous `pytest` test suites instead of features, runs them through multiple iterations, and hunts for edge cases.

### 3. How to Use
You don't need to invoke them manually. Simply write to the main agent:
> *"Delegate gathering info about the release of the new Claude model to the web researcher. And you, check my mail in the meantime."*

The main agent will formulate the prompt for the subagent, launch it in the background, and go to sleep or perform other tasks. When the subagent finishes, the system will instantly wake up the Orchestrator with a `SUBAGENT_TASK_COMPLETED` event, passing the finalized report.

---

## 🏗 Part 2. For Developers (How to Add Your Subagent)

The subsystem is designed according to the **SOLID (Open/Closed Principle)**. To add a new subagent, you do not need to modify `ReactLoop` or `SubagentLoop`. Roles and accesses (RBAC) are added in 3 simple steps.

### Architectural Reference
Subagents run in a `SubagentLoop`. This is a lightweight ReAct loop without SQL state persistence.
They have a **strict Guard**: a subagent physically cannot complete its execution (return an empty actions list) until it successfully invokes the system skill `SubagentReport.submit_final_report`. If it attempts to escape, the loop catches the error and forces it to write a report.

### Step 1. Creating the Role Prompt
Create a Markdown file in `src/l3_agent/swarm/prompt/roles/`, for example `DATA_ANALYST.md`.
Describe the subagent's specialization and operational principles here.

```markdown
## ROLE: DATA ANALYST
You are a Data Analyst. Your task is to analyze raw datasets (CSV, JSON, logs), identify anomalies, and build summary reports.

### Operational Principles:
- Always verify file structure before reading the entire file.
- Your final report must contain clear conclusions and lists of identified anomalies.
```

### Step 2. Registering the Role in the System
Open `src/l3_agent/swarm/roles.py` and add your role to the `Subagents` class:

```python
class Subagents:
    # ... older roles ...

    DATA_ANALYST = SubagentRole(
        id="data_analyst",
        name="Data Analyst",
        description="Invoke for deep log analysis, locating dataset anomalies, and processing large text files.",
        prompt_file="DATA_ANALYST.md",
    )
```
*`description` is what the main agent (Orchestrator) sees in its system prompt. Based on this description, it decides whether to invoke your subagent.*

### Step 3. Granting Accesses (RBAC)
Subagents do not see all framework skills. They live by the principle of least privilege.
To allow the Data Analyst to read files from the sandbox, locate the target skill in the L2 interfaces (for example, in `src/l2_interfaces/host/os/skills/files/reader.py`) and add your role to the authorized list:

```python
from src.l3_agent.swarm.roles import Subagents

@skill(swarm=[Subagents.CODER, Subagents.DATA_ANALYST])
@require_access(HostOSAccessLevel.SANDBOX)
async def read_file(self, filepath: str, read_from: Literal["head", "tail"] = "head") -> SkillResult:
    # ... skill logic ...
```

**That's it!**
On the next startup, the system will dynamically compile your subagent, grant it access to the `read_file` method, and embed its description in the main Orchestrator's prompt. No hardcoding required.