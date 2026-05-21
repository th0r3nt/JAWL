# Code Graph Configuration (Agentic Introspection)

The `code_graph` interface provides the agent with "X-ray vision" for working with codebases (repositories).

## How it works
When the agent invokes the `index_codebase` skill, the system (via the built-in Python `ast` module) scans the specified directory and splits all `.py` files into logical nodes (Files, Classes, Functions).
1. **Dependency Graph:** Nodes are linked in KuzuDB by `IMPORTS`, `CONTAINS`, and `DEFINES` edges. This allows the agent to compute dependencies between files (for example, to know which tests need to be updated after refactoring).
2. **Semantic Search:** Docstrings of all functions and classes are processed through a local embedding model (FastEmbed) and saved into the Qdrant vector database. This allows the agent to search for the required piece of code not by its exact name, but by its **meaning**.

*Note: The similarity threshold for code search is extracted from the general vector database settings (`settings.yaml` -> `system.db.vector.similarity_threshold`).*

## Parameters (`code_graph`)

* **`enabled`**: `true` / `false`. Enables the subsystem. If disabled, the agent loses codebase indexing and navigation skills.
* **`max_search_results`**: Number of results returned by default when using the `search_code_semantic` skill. Protects the agent's context window from overflowing if there are too many matches.
* **`max_structure_items`**: Limit on the number of classes and functions returned when requesting file structure (`get_file_structure`). If a file (God Object) contains 1000 methods, the output will be truncated to save tokens.
* **`exclude_dirs`**: List of directory names fully ignored by the parser during indexing.
  * *Why this is needed:* Indexing virtual environments (`venv`) or directories with temporary files (`node_modules`, `__pycache__`) would clog the database with thousands of irrelevant third-party functions, slowing down searches and confusing the agent. Always add heavy, non-relevant folders to this list.