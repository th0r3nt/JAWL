# Web HTTP Configuration

The lightweight `http` interface provides the agent with skills to send raw HTTP requests (`GET`, `POST`, etc.) and download files directly to the `sandbox/_system/download/` folder. It is ideal for working with custom REST APIs without spawning a heavy headless browser.

## Parameters (`web.http`)

* **`enabled`**: `true` / `false`.
* **`request_timeout_sec`**: Timeout in seconds for waiting for server responses.
* **`max_response_chars`**: Strict limit on response character length. If a server returns a giant 10 MB JSON payload, the system automatically truncates it to prevent a `Context Window Exceeded` crash on the language model side.