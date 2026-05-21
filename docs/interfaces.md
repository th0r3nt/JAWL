# 🔌 JAWL L2 Interfaces: User and Developer Guide

The **L2 (Interfaces)** layer represents the sensory organs and hands of the agent. Through interfaces, the agent reads files, sends messages, makes commits, and surfs the Internet.

This document is divided into two parts: for **users** (how to configure what is ready) and for **developers** (how to write your own interface without breaking the architecture).

---

## 🛠 Part 1. For Users (How to Enable and Configure)

All interfaces are disabled by default to prevent the agent from accessing places it wasn't requested.

### 1. Enabling via CLI (Recommended)
The easiest way to manage interfaces is to run the `jawl.py` script and select from the main menu:
👉 **"⚙️ Setup Wizard"**
There, you can enable and disable modules using space/enter. Changes will be automatically written to the `config/interfaces.yaml` file.

### 2. Keys and Authorization (.env)
Some interfaces require API keys or passwords to work. These must be specified in the `.env` file (create it from `.env.example` if it doesn't exist yet).
- **Telegram (Telethon)**: Requires `TELETHON_API_ID` and `TELETHON_API_HASH` (obtained at my.telegram.org).
- **Telegram (Aiogram)**: Requires `AIOGRAM_BOT_TOKEN` from @BotFather.
- **GitHub**: Requires a classic `GITHUB_TOKEN` (PAT) with `repo` and `read:user` scopes.
- **Email**: Requires a login and a **dedicated App Password**. A regular mail password will not work - Google/Yandex will block access.

### 3. Manual Configuration (interfaces.yaml)
For fine-tuning (limits, timeouts, access rights), open `config/interfaces.yaml`.
*The most important parameter is `access_level` in `host_os`*. It determines whether the agent can wipe your hard drive or if it is locked inside the `sandbox/` folder.

---

## 🏗 Part 2. For Developers (How to Create Your Own Interface)

We strictly adhere to **SOLID** and layer isolation. The agent (L3) knows nothing about libraries (L2). It communicates with the interface only through registered skills (Skills) and sees its status via the dashboard (L0 State).

The system uses the **Plugin Discovery** pattern. Creating a new interface (for example, `Discord`) always consists of 5 steps.

### Step 1. Folder Structure and State (L0)
Create a folder in `src/l2_interfaces/discord/` with the following structure:
```text
discord/
├── skills/
│   ├── __init__.py
│   └── messages.py     # Skills (agent's hands)
├── __init__.py
├── plugin.py           # Plugin initializer
├── client.py           # Connection manager
└── state.py            # Dashboard (L0 State)
```

Open `state.py` and add the state class.
**Rule:** State must be passive. No I/O operations. Only data caching.

```python
class DiscordState:
    def __init__(self, recent_limit: int = 10):
        self.is_online = False
        self.last_messages = "Empty."
```

### Step 2. Writing the Client (`client.py`)
The client encapsulates the connection to the API and stores a reference to the state (L0).

```python
from typing import Any
from src.l2_interfaces.discord.state import DiscordState

class DiscordClient:
    def __init__(self, state: DiscordState, token: str):
        self.state = state
        self.token = token

    async def get_context_block(self, **kwargs) -> str:
        desc = "Description: Discord API connector."
        if not self.state.is_online:
            return f"### DISCORD [OFF]\n{desc}\nThe interface is disabled."
        return f"### DISCORD [ON]\n{desc}\nRecent messages:\n{self.state.last_messages}"
```

### Step 3. Writing the Skills (`skills/messages.py`)
Skills are what the agent can invoke.
**Rule:** Skills must return a `SkillResult` object. All methods intended for the agent are marked with the `@skill()` decorator.

```python
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.discord.client import DiscordClient

class DiscordMessages:
    def __init__(self, client: DiscordClient):
        self.client = client

    @skill()
    async def send_message(self, channel_id: int, text: str) -> SkillResult:
        """Sends a text message to the specified Discord channel."""
        try:
            # send logic via self.client...
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Send error: {e}")
```

### Step 4. Plugin Assembly (`plugin.py`)
In `plugin.py`, we bind everything together. The system will automatically find this file and load the plugin if it is enabled in `interfaces.yaml`.

```python
from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig

from src.l2_interfaces.discord.state import DiscordState
from src.l2_interfaces.discord.client import DiscordClient
from src.l2_interfaces.discord.skills.messages import DiscordMessages

class DiscordPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "DISCORD"

    @property
    def description(self) -> str:
        return "Connects to Discord API."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        # To support this, you need to add discord: DiscordConfig to settings.py/InterfacesConfig
        return getattr(config, "discord", False)

    def setup(self, container: SystemContainer, env_vars: Dict[str, Optional[str]]) -> List[Any]:
        token = env_vars.get("DISCORD_TOKEN")
        if not token:
            self.register_off_provider(container.context_registry)
            return []

        state = DiscordState()
        container.l0_states["discord"] = state
        
        client = DiscordClient(state=state, token=token)
        
        # Register skills
        register_instance(DiscordMessages(client))
        
        # Register context provider
        container.context_registry.register_provider(
            name=self.name.lower(), 
            provider_func=client.get_context_block, 
            section=ContextSection.INTERFACES
        )
        
        main_logger.info("[Discord] Interface loaded.")
        return [client] # Return components that have start() and stop() methods
```

### 📌 Good Interface Checklist:
- [ ] **No token hardcoding**. Everything is extracted from `.env` and passed through arguments.
- [ ] **Context protection**. If a function reads history or files, use `truncate_text` to prevent burning the LLM's token limit with huge text blocks.
- [ ] **DRY & KISS**. Move shared utilities (for example, URL parsing) to `src/utils/`.