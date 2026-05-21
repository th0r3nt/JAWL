# Internal Motivation and Psychology (Drives)

The `Drives` module is a mathematical model simulating human needs and the psychological state of the agent. It prevents system "idling" during periods when no direct commands are received from the user.

The dry mathematics of the deficit is translated into a **5-step semantic self-perception matrix**.

## How It Works

### 1. Deficit Mathematics
Deficit accumulation is defined by:
* `decay_interval_sec`: Interval duration in seconds.
* `decay_rate`: Deficit growth rate percentage per single interval.
* `dynamic_reduction`: Non-linear model. If `true`, need satisfaction scales dynamically. The longer the agent remained in a "stressed" state (high deficit), the more active steps it will have to execute to return to a satisfied, balanced state.

*Example:* If the interval is 1200 sec (20 minutes) and `decay_rate` = 10.0, the deficit grows by 10% every 20 minutes.

### 2. Semantic States
The agent does not see dry percentages. The deficit percentage is translated into semantic self-perceptions (ranging from "Intellectual Satiety" to "Acute Information Deprivation") with a step of 20%.
Sensing the growing discomfort in its system context, the agent proactively calls the `satisfy_drive` skill to reduce the deficit (for example, surfs the web for news to satisfy `Curiosity`), writing a reflection explaining how the action resolved the need.

## Fundamental and Custom Motivators
The system is shipped with three pre-configured fundamental drives:
- **Curiosity**: Need for data expansion and information harvesting.
- **Social**: Need to communicate and monitor connection channels.
- **Mastery**: Striving to complete tasks, run tests, and clean up databases.

*In addition, the agent can programmatically create custom drives for specific operational needs.*

## Parameters (`system.db.sql.drives`)
* **`enabled`**: `true` / `false`. Enables the drives subsystem.
* **`pause_on_offline`**: `true` / `false`. Downtime compensation. If the system was shut down, upon startup it calculates the offline duration and shifts satisfaction timers. The agent won't wake up with a panic deficit of everything after long offline periods.
* **`dynamic_reduction`**: `true` / `false`. Enables the non-linear stress accumulation model.
* **`max_reflections_history`**: How many of the latest reflections are kept in the prompt.
* **`max_custom_drives`**: Limit on the number of custom drives the agent is allowed to create.
* **`fundamental`**: Fundamental needs configurations.
  - Each need (`curiosity`, `social`, `mastery`) is configured individually:
  - **`enabled`**: Enables or disables the need.
  - **`decay.rate`**: Growth rate percentage.
  - **`decay.interval_sec`**: Interval duration in seconds.