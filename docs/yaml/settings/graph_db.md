# Graph DB Configuration (Knowledge Graph)

The graph memory module (`graph_db`) based on KuzuDB allows the agent to construct logical and semantic maps of concepts. Unlike vector memory, which searches for text similarity, graph memory establishes rigid causal connections and hierarchies (Knowledge Graph).

### Parameters (`system.graph_db`):
* **`max_nodes`**: Maximum number of allowed concepts (Concept nodes) in the database. Protects disk space and RAM from growing indefinitely if the agent starts hallucinating nodes.
* **`max_edges_per_node`**: Limitation on the number of links allowed per single node. Prevents the emergence of "Superstars" (nodes linked to everything), which during neighborhood lookups would overflow the agent's context window.