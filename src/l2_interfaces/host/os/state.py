"""
Stores the state of the Host OS.

Telemetry, time, uptime.
Updated by listeners (os/events.py) in the background.
"""


class HostOSState:
    """
    Stores the state of the Host OS.
    Telemetry, time, uptime.
    Updated by listeners (os/events.py) in the background.
    """

    def __init__(self) -> None:
        self.is_online = False

        # Static data (determined once upon start)
        self.os_info = "Unknown."  # Windows/Linux/Mac
        self.cpu_name = "unknown CPU"
        self.total_ram_gb = 0.0

        # Dynamic data
        self.datetime = "Unknown."  # Time
        self.uptime = "Unknown."  # Host PC uptime
        self.telemetry = "No available telemetry."  # CPU, RAM, processes
        self.sandbox_files = "Unknown."  # Current files in Sandbox
        self.framework_files = "Unknown."  # JAWL directory tree
        self.tracked_dirs_trees = "No tracked directories."
        self.active_daemons = "No running daemons."

        self.polling_interval = "Unknown."

        self.opened_workspace_files: set[str] = set()  # Files opened in the agent "editor"
        self.recent_file_changes: list[str] = []  # Cache of the latest diffs
