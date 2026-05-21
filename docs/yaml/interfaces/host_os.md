# Host OS Access Levels (`host.os.access_level`)

The agent's access to the file system is controlled by the built-in `Gatekeeper` component. It intercepts all path-related calls, prevents Path Traversal attacks (escaping directory bounds via `../` sequences), and blocks attempts to read or modify `.env` files containing API keys (if the `env_access` parameter is set to `false`).

* **0 (SANDBOX):** Maximum safety. The agent has the right to read and write files strictly inside the `sandbox/` directory.
* **1 (OBSERVER):** Tester mode. The agent can read (Read) the framework's source code, but write (Write) operations are allowed strictly inside the `sandbox/` directory.
* **2 (OPERATOR):** Developer mode. The agent receives read and write privileges inside the entire JAWL project directory. Modifying the system's source code requires an active Deploy Session.
* **3 (ROOT):** Full access. The agent receives read, write, and delete privileges on any files on the host machine (within the bounds of the user who started the script), as well as the right to execute raw shell commands. **It is highly discouraged to activate this level on your primary workstation.**

### Deploy Sessions (Secure Self-Modification)
If the agent possesses `OPERATOR` access level or higher, and the `require_deploy_sessions` parameter is set to `true`, the system protects itself from fatal syntax crashes.
Before modifying system code, the agent must open a "Deploy Session". The system creates a Copy-on-Write backup of the modified files. Upon committing the changes, the framework automatically runs a syntax analyzer and `pytest`. If any tests fail, the agent receives the Traceback error and consumes one retry attempt. If the attempts limit (`deploy_max_retries`) is exhausted, the system automatically triggers a Rollback (restores the backed-up files to their initial state).

# Host OS Limits (`host.os`)

These parameters protect the system prompt from being overloaded by giant directory trees and verbose logs while the agent is operating on the host machine.

* **`framework_tree_depth`**: The depth to which the agent can view the directory tree of the framework itself (JAWL). `1` — root folder only, `2` — root and nested folders, etc.
* **`monitoring_interval_sec`**: Frequency (in seconds) of polling telemetry (CPU/RAM) and file system changes.
* **`file_read_max_chars`**: Character limit when reading files (the `read_file` skill). If a file is larger, it will be truncated.
* **`file_list_limit`**: Maximum number of files/folders displayed when scanning directories.
* **`file_diff_max_chars`**: Character limit for the `git-diff` log injected into the dashboard after file modifications.
* **`top_processes_limit`**: Number of active processes (sorted by memory consumption) displayed in the telemetry block.
* **`workspace_max_opened_files`**: Maximum number of "editor tabs" (files currently held open by the agent in its context).
* **`recent_file_changes_limit`**: How many of the latest file diffs are preserved in memory (MRU cache).
* **`workspace_max_file_chars`**: Maximum size of a file (in characters) that can be held open in the agent's editor tabs.