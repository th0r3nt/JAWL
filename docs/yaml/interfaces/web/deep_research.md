# Deep Research Configuration (`web.search.deep_research`)

The `DeepResearch` skill allows the main agent and subagents to conduct mass parallel search and data harvesting on the web. These settings protect you from API rate limits and context window overflows.

* **`max_queries`**: Maximum number of search queries executed in parallel (prevents IP/API bans in DuckDuckGo/Tavily).
* **`max_results_per_query`**: Maximum number of link results extracted per single search query.
* **`max_pages_to_read`**: Overall limit of unique web pages to download and parse (prevents downloading half of the Internet).
* **`total_max_chars`**: **Critical parameter.** Maximum character length of text returned by the research. The module dynamically splits this budget across all parsed pages, truncating each page to ensure the LLM's context window does not overflow.