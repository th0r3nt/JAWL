"""
L0 State for the Calendar interface (Time Management).
"""


class CalendarState:
    """
    Stores the state of the agent's calendar.
    Displays upcoming scheduled events and timers.
    """

    def __init__(self):
        self.is_online = False
        self.upcoming_events = "No events."
