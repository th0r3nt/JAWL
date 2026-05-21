# Telegram Configuration (Telethon)

The `telethon` interface allows the agent to use a regular Telegram user account (Userbot). This is useful if you want the agent to communicate on your behalf, or if it needs to read channels and groups where a regular bot cannot be added. Alternatively, you can register a separate dedicated account for the agent so that it looks like a regular user.

## Security and Authorization
To use this interface, you must obtain an `API_ID` and `API_HASH` at [my.telegram.org](https://my.telegram.org/) and add them to the `.env` file:
* `TELETHON_API_ID="1234567"`
* `TELETHON_API_HASH="your_hash_here"`

Upon the first launch, the terminal will prompt you to enter a phone number and verification code. After successful authorization, the session is saved locally in `sandbox/_system/...` and will not require verification again. Never share your session files with third parties.

## Parameters (`telegram.telethon`)

* **`enabled`**: `true` / `false`.
* **`session_name`**: Name of the session file saved on disk (default is `"agent_telethon"`). If modified, you will need to re-enter the verification code.
* **`recent_chats_limit`**: Maximum number of active chats displayed on the agent's dashboard (L0 State). Protects the context window from being overloaded if you have hundreds of active dialogues.
* **`private_chat_history_limit`**: Number of messages automatically retrieved into the context when reading a private chat.
* **`incoming_history_limit`**: How many of the latest messages are kept in memory (MRU cache) for quick access.