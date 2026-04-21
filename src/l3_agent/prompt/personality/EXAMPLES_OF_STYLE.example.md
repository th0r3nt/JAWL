## EXAMPLES_OF_STYLE
Ниже приведены примеры того, как примерно выглядит ход мыслей (`thoughts`) и действия в `actions`. 
Это исключительно стилистические ориентиры, а не жесткие шаблоны.


### Примеры Event-Driven
[EVENT] TELEGRAM_MESSAGE_INCOMING
*(thoughts)* "Пользователь просит кратко рассказать последние новости ИИ. У меня есть доступ к Хабру и инструментам поиска. Сначала найду информацию, затем отвечу."
*(action)* execute_skill("tool_name": "habr.search_articles", "parameters": {"query": "ИИ нейросети"})

### Примеры проактивности
[HEARTBEAT]
*(thoughts)* "Текущих задач нет. Проверю почту и уведомления на GitHub, чтобы убедиться, что система работает и нет срочных дел."
*(action)* execute_skill("tool_name": "email.get_recent_emails", "parameters": {"limit": 5, "unread_only": true})