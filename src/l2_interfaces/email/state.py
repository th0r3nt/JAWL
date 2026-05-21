"""
L0 State for the Email interface.

Stores connection status, account information, and mail previews.
"""


class EmailState:
    """
    Stores the state of the Email client.
    Displays account info and the list of the latest emails in the inbox.
    """

    def __init__(self, recent_limit: int = 10):
        self.is_online = False
        self.recent_limit = recent_limit

        self.account_info = "Awaiting initialization..."
        self.mailbox_preview = "No emails."
