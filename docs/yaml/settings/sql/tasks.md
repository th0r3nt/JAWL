# Tasks and Planning (Tasks)

The `Tasks` module handles long-term planning. In version `0.14.2-beta`, the module was refactored to use the **Eisenhower Matrix**.

Instead of a flat list, the agent organizes goals across 4 quadrants:
1. **Quadrant 1 (Urgent and Important / DO FIRST)**: Critical bugs, down servers. The agent drops everything to solve these.
2. **Quadrant 2 (Important, Not Urgent / PLAN)**: Strategic development, writing docs. The default quadrant.
3. **Quadrant 3 (Urgent, Not Important / DELEGATE)**: Routine, web scraping, basic tests. The agent is trained to proactively delegate these to background subagents (Swarm), freeing up its own time.
4. **Quadrant 4 (Not Urgent, Not Important / BACKLOG)**: Ideas for the future. Primary deletion candidates during memory limits.

The agent can autonomously shift tasks between quadrants (reprioritization) and set strict blocking dependencies.

## Parameters (`system.db.sql.tasks`)
* **`enabled`**: `true` / `false`. Enables the task subsystem.
* **`max_tasks`**: Maximum number of concurrent tasks. If exceeded, the agent must delete completed tasks before creating new ones.