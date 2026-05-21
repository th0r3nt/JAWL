"""
L0 State for the Web RSS interface.

Stores tracking status and the latest news feed preview.
"""


class WebRSSState:
    """Stores the state of the RSS module, showing latest activity and news."""

    def __init__(self, recent_limit: int = 5):
        self.is_online = False
        self.recent_limit = recent_limit
        self.feeds_status = "Awaiting initialization..."
        self.latest_news = "No loaded news."
