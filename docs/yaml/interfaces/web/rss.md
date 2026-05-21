# RSS Feed Configuration (Web RSS)

The Web RSS interface is designed for automatic tracking of news, articles, and releases via RSS and Atom feeds.

## How It Works
The interface does not require the agent to waste active tokens on regular requests:
1. A background process polls the configured feeds at the frequency specified in `polling_interval_sec`.
2. Titles of the latest entries are printed to the agent's L0 State dashboard to maintain general context.
3. Upon detecting a new unique publication, the system publishes a `BACKGROUND` level event `RSS_NEW_ENTRY` to the event bus.
4. The agent sees the notification, and if the topic is relevant to its current goals or interests, it can invoke the `read_rss_feed` skill to retrieve the full, HTML-stripped text of the article.

## Pre-configured Feeds Examples

Below is a list of popular feeds that can be added to the `feeds` block in `interfaces.yaml`:

**Technology and IT:**
- Habr (All streams): `https://habr.com/ru/rss/all/all/`
- Habr (Artificial Intelligence Hub): `https://habr.com/ru/rss/hub/artificial_intelligence/`
- TechCrunch: `https://techcrunch.com/feed/`

**Academic Publications (ArXiv):**
- Computer Science - AI: `https://export.arxiv.org/rss/cs.AI`
- Computer Science - Machine Learning: `https://export.arxiv.org/rss/cs.LG`

**GitHub Repository Releases:**
To subscribe to releases of any repository, append `.atom` to the end of the releases page URL:
- Python Releases: `https://github.com/python/cpython/releases.atom`
- JAWL Releases: `https://github.com/th0r3nt/JAWL/releases.atom`

**YouTube Channels:**
You only need to know the Channel ID to track videos:
- `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`