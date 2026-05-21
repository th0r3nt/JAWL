# Tree of Thoughts Configuration (Tree of Thoughts)

The `Tree of Thoughts` (MCTS — Monte Carlo Tree Search) module equips the agent with multi-level strategic planning capabilities. Instead of impulsively executing the first idea that comes to mind in a ReAct manner, the system generates a **fractal tree of simulations**, evaluating multiple macro-strategies and nested micro-scenarios (for example, "what if everything goes as planned" versus "system failure simulation") BEFORE executing physical actions.

The `v0.14.3-beta` version updated ToT to a recursive analysis model: each branch contains a strict list of advantages (`pros`) and disadvantages/risks (`cons`) instead of abstract complexity ratings.

## Parameters (`system.tree_of_thoughts`)

* **`enabled`**: `true` / `false`. Enables the strategic planning subsystem.
* **`llm_model`**: Model identifier (it is highly recommended to use fast, large-context models like `gemini-1.5-flash` or `gpt-4o-mini`).
* **`mode`**: Activation mode:
  * `"manual"` — The tree is simulated only when the `deep_think` skill is explicitly invoked by the agent.
  * `"auto"` — Automatic simulation on the first step of the ReAct cycle and subsequently once every `auto_interval_steps`.
  * `"hybrid"` — Combined mode (recommended).
* **`auto_interval_steps`**: Step frequency for automatic subconscious activation (in ReAct steps).

### Tree Geometry (Simulation Architecture)

These parameters define the "power" of the reasoning simulation. **Warning:** increasing these values leads to exponential token consumption growth.

* **`branches`**: Number of **macro-strategies** (top-level branches). Optimal: `2-3`.
* **`simulations_per_branch`**: Number of **nested scenarios** simulated per each branch on each nesting level. Optimal: `2`.
* **`max_depth`**: Maximum **simulation depth**.
  * `1` — Flat list of strategies.
  * `2` — Strategy -> Scenarios (1.1, 1.2).
  * `3` — Strategy -> Scenarios -> Future developments (1.1.1, 1.1.2).
  * *Recommended: `2`*.

## Interaction (the `deep_think` skill)

The main agent can initiate a deep thought cycle at any moment by calling:
`deep_think(task_description="Describe a specific problem to analyze")`

Passing a `task_description` focuses the subconscious on a specific bottleneck (for example, "evaluate risks of changing the authentication method") instead of a general analysis of the entire state.

## Result Analysis (Pros & Cons)

Unlike older versions, the model does not output abstract "complexity: medium" ratings. Instead, it generates:
1. **Pros**: Clear advantages and arguments "FOR" choosing this path.
2. **Cons**: Potential bugs, security risks, and reasons why this path might fail.

The Orchestrator (Main Agent) must analyze these lists before choosing its final physical actions in the ReAct cycle.