# Lifecycle and Proactivity (`system`)

Manages the agent's operating rhythm (Heartbeat) and its proactivity.

* **`heartbeat_interval`**: Base sleep interval (in seconds) in the absence of external incoming events. For example, `600` means that the agent is guaranteed to wake up once every 10 minutes to verify its motivators (Drives) and run background routines.
* **`continuous_cycle`**: `true` / `false`. If `true`, the agent does not sleep at all. As soon as it concludes one ReAct reasoning loop, it instantly starts the next one. **Warning:** burns API tokens at an astronomical rate.
* **`proactive_guidance`**: `true` / `false`. Injects an insistent prompt instruction into scheduled Heartbeat wakeups, urging the agent to find productive tasks (refactoring, information harvesting, database maintenance) in the absence of direct user commands.