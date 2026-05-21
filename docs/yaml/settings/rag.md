# Hybrid Search and Context Memory (Vector-Graph RAG)

The `RAG` (Retrieval-Augmented Generation) subsystem in JAWL utilizes an innovative **hybrid mechanism (Vector-Graph RAG)**. It combines semantic vector search (Vector DB) with explicit logical connections from the knowledge graph (Graph DB).

## How It Works (Vector-Graph RAG)
When the agent receives a message (or reflects on a task), the RAG orchestrator extracts search anchors (keywords) from the text. Then, an iterative retrieval cycle of depth (`depth_limit`) is initiated:

1. **Step 1:** Vector DB retrieves semantic matches while Graph DB extracts known concept nodes.
2. **Step 2 (Semantic Synchronization):** If a retrieved Vector DB text fragment mentions another graph node, the system automatically pulls that node and its adjacent relations. Conversely, descriptions of newly found graph nodes are used as fresh search queries for the Vector DB.
3. **Result:** The agent receives a dense, clean summary of facts and their logical connection map in its `System Prompt`, permanently preventing "amnesia" on long runs.

## Settings (`system.context_depth.rag`)

* **`enabled`**: `true` / `false`. Enables or disables the automated recall system.
* **`extraction_engine`**: The entity extraction engine (`"flashtext"` or `"rapidfuzz"`).
  * `"flashtext"` — high-performance Aho-Corasick algorithm. Matches exact strings only. Recommended for large graphs (1000+ nodes) on English text.
  * `"rapidfuzz"` — fuzzy matching. Recognizes words in different cases and inflections. **Recommended for Russian language** and small/medium graphs.
* **`depth_limit`**: Depth of the recursive search (Vector-Graph RAG).
  * `1` — Direct lookup only (fast, saves CPU).
  * `2` — Optimal. The system resolves non-obvious second-level relationships (for example, a query "Matrix" finds the "Neo" node, and "Neo" pulls a vector fact about "Trinity").
  * `3+` — Deep research. Use with caution as it can cause exponential growth in computations (though limits protect the context).
* **`max_vector_blocks`**: Hard limit on the number of Vector DB facts injected into the system prompt. Protects against context length overflows.
* **`max_graph_nodes`**: Hard limit on the number of Graph DB nodes injected.
* **`max_query_chars`**: Maximum characters limit per a single text chunk. If the agent generates a giant thought, the `EntityExtractor` splits it into smaller chunks of `N` characters to keep the semantic density of generated embeddings high.