# Probabilistic Reasoning (Bayesian Hypotheses)

The `Hypotheses` module equips the agent with the ability to conduct deductive investigations based on Bayes' Theorem.

Instead of blind guessing or panicking when faced with a system failure (for example, a database crash or a weird code bug), the agent formulates a hypothesis, estimates its prior probability, and actively gathers clues. Each gathered clue (a ping command, a read log file) mathematically shifts the agent's confidence up or down.

## Parameters (`system.db.sql.hypotheses`)
* **`enabled`**: `true` / `false`. Enables the probabilistic reasoning module.
* **`max_hypotheses`**: Limit on the number of concurrent active hypotheses. The agent's operative context must remain clean, so it is forced to delete confirmed or refuted hypotheses before creating new ones.