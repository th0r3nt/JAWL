# Web Browser Configuration

The `browser` interface spins up a full asynchronous Chromium instance on the host machine via Playwright. Unlike `search`, the browser can execute JavaScript, manage cookies, and interact with complex SPA websites.

If Chromium binaries are missing on the system, the client will automatically download them on the first launch (this might take a few minutes).

## Features (Lazy Loading)
The browser does not stay in memory permanently. It is launched only when the agent invokes a navigation or interaction skill. The page element tree (AOM) is converted into a flat Markdown structure and injected into the agent's dashboard.

## Parameters (`web.browser`)

* **`enabled`**: `true` / `false`.
* **`headless`**: `true` / `false`. If `true` (recommended), the browser runs in the background without drawing windows. If `false`, you will physically see how the agent moves the cursor and clicks on the page (useful for debugging anti-fraud bypasses on complex sites).
* **`timeout_sec`**: Maximum wait timeout for loading page elements.
* **`idle_timeout_sec`**: Idle timeout (in seconds). If the browser remains unused for N seconds, a background daemon automatically closes Chromium to free up RAM.