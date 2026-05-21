# GitHub Configuration

The GitHub interface provides the agent with access to the REST API (managing repositories, reading code, Issues, Pull Requests). In conjunction with local Git skills (cloning into the sandbox and making commits), this allows the agent to act as a full-fledged Software Engineer.

## Authorization and Operating Modes
In `.env`, specify `GITHUB_TOKEN` (use a classic Personal Access Token with `repo` and `read:user` scopes).

* **`agent_account: true`**: Full-access mode. The agent uses the token for authorization. It can read private repositories, create Issues, comment on code, make forks, and push commits. API limit is 5000 requests per hour.
* **`agent_account: false`**: Read-Only mode. No token is used. The agent can only read public repositories. The API limit is extremely strict - 60 requests per hour (only enough for basic trends lookup).

## Parameters (`github`)

* **`request_timeout_sec`**: Timeout for waiting responses from GitHub servers.
* **`history_limit`**: MRU cache limit. How many of the latest actions (requests) are stored in the history on the dashboard.
* **`polling_interval_sec`**: Frequency (in seconds) of background polling. How often the agent will check for new notifications (mentions) and events in watched repositories (Watchers).