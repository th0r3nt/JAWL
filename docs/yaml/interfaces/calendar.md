# Calendar Configuration

The `calendar` interface manages the agent's time and schedule. It handles one-time, interval, and recurring timers/alarms.

The calendar stores data locally in `sandbox/_system/interfaces/calendar/events.json`.

## Wakeup Mechanism
The agent does not check the time itself (that would waste API tokens). Instead, a lightweight background daemon handles this. When the time comes, the daemon publishes a `SYSTEM_CALENDAR_ALARM` event to the event bus. `Heartbeat` catches it, immediately interrupts the agent's sleep, and passes information about which alarm triggered.

## Parameters (`calendar`)

* **`enabled`**: `true` / `false`.
* **`polling_interval_sec`**: How often (in seconds) the background daemon checks current time against the timers in the JSON file. Default is once per minute (60).
* **`upcoming_events_limit`**: How many upcoming events to display on the agent's dashboard (L0 State) so it can see its daily plans.