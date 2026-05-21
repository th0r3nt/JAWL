# Telegram Configuration (Aiogram)

The `aiogram` interface is designed for the classic Bot API. It is ideal if the agent needs to act as a classic support assistant, bot manager, or chat moderator.

## Authorization
Create a bot with [@BotFather](https://t.me/BotFather), copy the token, and add it to the `.env` file:
* `AIOGRAM_BOT_TOKEN="123456789:ABCDefgh..."`

Unlike Telethon, bots do not have access to full chat histories. The agent will only "see" messages that arrived after its startup.

## Parameters (`telegram.aiogram`)

* **`enabled`**: `true` / `false`.
* **`recent_chats_limit`**: Maximum number of active chats displayed on the dashboard (L0 State). If the bot is added to 500 groups, this limit prevents the list from burning your entire LLM token quota.