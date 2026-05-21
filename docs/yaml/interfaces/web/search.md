# Web Search Configuration

The `search` interface grants the agent internet access. It is designed using the Strategy pattern, allowing you to swap out search engines and parsers to fit your needs.

## Parameters (`web.search`)

* **`search_engine`**: The engine used to look up URLs.
  * `"duckduckgo"` (DDG) — free, does not require API keys. Subject to Cloudflare rate limits (banned easily on intensive parallel queries). Restricted by an internal semaphore.
  * `"tavily"` — specialized search engine optimized for AI agents. Stable, fast, and reliable. Requires `TAVILY_API_KEY` specified in `.env` (free tier available). Highly recommended.
* **`reader_engine`**: Webpage content parser (converting raw HTML to clean text).
  * `"jina"` — calls the remote proxy service `r.jina.ai`. Excellent at converting sites into Markdown, bypasses many captchas.
  * `"trafilatura"` — parses raw HTML fully locally on the host machine. Free, fast, private, but might fail on heavy JS-heavy React/Vue SPA websites.
* **`request_timeout_sec`**: Network requests timeout (in seconds).
* **`max_page_chars`**: Maximum character length allowed when parsing a single page. Everything exceeding this limit is strictly truncated.