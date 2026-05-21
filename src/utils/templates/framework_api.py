import json
import uuid
import time
from pathlib import Path


def send_event(message: str, payload: dict = None):
    """
    Sends an event (Event) to the main JAWL agent.

    Important: Invoking this function wakes up the agent, interrupting its sleep.
    Useful for important notifications that require immediate reaction and actions.
    """

    if payload is None:
        payload = {}
    _write_event({"message": message, "payload": payload})


def update_dashboard(name: str, markdown_content: str):
    """
    Creates or updates a custom block in the agent's system context (L0 State).
    This function passively updates the context.
    """

    payload = {
        "_jawl_internal_type": "dashboard_update",
        "name": name,
        "content": markdown_content,
    }
    _write_event({"message": f"Update dashboard {name}", "payload": payload})


# System function, do not invoke
def _write_event(data: dict):
    """
    Internal function for atomic event writing to the IPC directory.
    """

    events_dir = Path(__file__).parent / ".jawl_events"
    events_dir.mkdir(parents=True, exist_ok=True)

    event_id = str(uuid.uuid4())
    temp_path = events_dir / f"{int(time.time())}_{event_id}.tmp"
    file_path = events_dir / f"{int(time.time())}_{event_id}.json"

    with open(temp_path, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False)

    temp_path.rename(file_path)


"""
=============================================================================
EXAMPLES OF USE
=============================================================================

Example: quiet dashboard
-----------------------------------------------------
import time
from framework_api import update_dashboard

def crypto_monitor():
    while True:
        # Imagine there is a request logic to the exchange API here...
        btc_price = 65000
        
        content = f"**BTC**: ${btc_price}\\n_Updated: {time.ctime()}_"
        
        # The agent will not wake up, but will see these prices in the context on the next tick
        update_dashboard(name="Crypto Market", markdown_content=content)
        
        time.sleep(300) # Wait 5 minutes

Example: active alert
-----------------------------------------------------
import time
from framework_api import send_event

def server_watchdog():
    while True:
        # Imagine we are pinging the server...
        server_is_down = True 
        
        if server_is_down:
            # This event will instantly wake up the agent to fix the server
            send_event(
                message="Critical error: Database is unavailable.", 
                payload={"server": "db_main", "error": "Timeout"}
            )
            break # Exit so as not to spam events every second
            
        time.sleep(60)
"""
