"""
L0 State for the Web Browser interface.

Stores open status, current URL, page title, and the accessibility viewport snapshot.
"""


class WebBrowserState:
    """
    Stores the state of the full web browser (Playwright).
    Displays the current URL and the accessibility tree (AOM) of the current page.
    """

    def __init__(self):
        self.is_online = False
        self.is_open = False

        self.current_url = "None"
        self.page_title = "None"
        self.viewport = "Browser is closed."

        self.history: list[str] = []

    def add_history(self, action: str):
        self.history.insert(0, action)
        if len(self.history) > 10:
            self.history.pop()
