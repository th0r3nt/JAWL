# 🔌 Интерфейсы (L2) в JAWL: Руководство пользователя и разработчика

Слой **L2 (Interfaces)** - это органы чувств и руки агента. Через интерфейсы агент читает файлы, отправляет сообщения, делает коммиты и сёрфит интернет. 

Этот документ разделен на две части: для **пользователей** (как настроить готовое) и для **разработчиков** (как написать свой интерфейс, не сломав архитектуру).

---

## 🛠 Часть 1. Для пользователей (Как включить и настроить)

Все интерфейсы по умолчанию выключены, чтобы агент не лез туда, куда его не просили. 

### 1. Включение через CLI (Рекомендуется)
Самый простой способ управлять интерфейсами - запустить скрипт `jawl.py` и в главном меню выбрать:
👉 **"⚙️ Мастер настройки"**
Там можно включать и выключать модули пробелом/энтером. Изменения автоматически запишутся в файл `config/interfaces.yaml`.

### 2. Ключи и авторизация (.env)
Некоторым интерфейсам для работы нужны ключи API или пароли. Их нужно прописать в файле `.env` (создайте его из `.env.example`, если его еще нет).
- **Telegram (Telethon)**: Нужны `TELETHON_API_ID` и `TELETHON_API_HASH` (берутся на my.telegram.org).
- **Telegram (Aiogram)**: Нужен `AIOGRAM_BOT_TOKEN` от @BotFather.
- **GitHub**: Нужен классический `GITHUB_TOKEN` (PAT) с правами `repo` и `read:user`.
- **Email**: Нужен логин и **специальный Пароль приложения (App Password)**. Обычный пароль от почты не подойдет - Google/Yandex заблокируют вход.

### 3. Ручная настройка (interfaces.yaml)
Для тонкой настройки (лимиты, таймауты, права доступа) откройте `config/interfaces.yaml`. 
*Самый важный параметр - `access_level` в `host_os`*. Он определяет, может ли агент стереть к чертям вам жесткий диск или он заперт в папке `sandbox/`.

---

## 🏗 Часть 2. Для разработчиков (Как создать свой интерфейс)

Мы строго соблюдаем **SOLID** и изоляцию слоев. Агент (L3) ничего не знает о библиотеках (L2). Он общается с интерфейсом только через зарегистрированные навыки (Skills) и видит его статус через приборную панель (L0 State).

Система использует паттерн **Plugin Discovery**. Создание нового интерфейса (например, `Discord`) всегда состоит из 5 шагов.

### Шаг 1. Структура папок и Стейт (L0)
Создайте папку в `src/l2_interfaces/discord/` со следующей структурой:
```text
discord/
├── skills/
│   ├── __init__.py
│   └── messages.py     # Навыки (руки агента)
├── __init__.py
├── plugin.py           # Инициализатор плагина
├── client.py           # Менеджер соединения
└── state.py            # Приборная панель (L0 State)
```

Откройте `state.py` и добавьте класс-хранилище.
**Правило:** Стейт должен быть пассивным. Никаких I/O операций. Только кэш данных.

```python
class DiscordState:
    def __init__(self, recent_limit: int = 10):
        self.is_online = False
        self.last_messages = "Пусто."
```

### Шаг 2. Написание Клиента (`client.py`)
Клиент инкапсулирует подключение к API и хранит ссылку на стейт (L0). 

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
        return f"### DISCORD [ON]\n{desc}\nПоследние сообщения:\n{self.state.last_messages}"
```

### Шаг 3. Написание Навыков (`skills/messages.py`)
Навыки - это то, что агент может вызывать. 
**Правило:** Навыки должны возвращать объект `SkillResult`. Все методы для агента помечаются декоратором `@skill()`.

```python
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.discord.client import DiscordClient

class DiscordMessages:
    def __init__(self, client: DiscordClient):
        self.client = client

    @skill()
    async def send_message(self, channel_id: int, text: str) -> SkillResult:
        """Отправляет текстовое сообщение в указанный канал Discord."""
        try:
            # логика отправки через self.client...
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Ошибка отправки: {e}")
```

### Шаг 4. Сборка (`plugin.py`)
В `plugin.py` мы связываем всё воедино. Система автоматически найдет этот файл и загрузит плагин, если он включен в `interfaces.yaml`.

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
        # Для этого нужно добавить discord: DiscordConfig в settings.py
        return getattr(config, "discord", False)

    def setup(self, container: SystemContainer, env_vars: Dict[str, Optional[str]]) -> List[Any]:
        token = env_vars.get("DISCORD_TOKEN")
        if not token:
            self.register_off_provider(container.context_registry)
            return []

        state = DiscordState()
        container.l0_states["discord"] = state
        
        client = DiscordClient(state=state, token=token)
        
        # Регистрируем скиллы
        register_instance(DiscordMessages(client))
        
        # Регистрируем провайдер контекста
        container.context_registry.register_provider(
            name=self.name.lower(), 
            provider_func=client.get_context_block, 
            section=ContextSection.INTERFACES
        )
        
        main_logger.info("[Discord] Интерфейс загружен.")
        return [client] # Возвращаем компоненты с методами start() и stop()
```

### 📌 Чек-лист хорошего интерфейса:
- [ ] **Никакого хардкода токенов**. Всё берется из `.env` и прокидывается через параметры.
- [ ] **Защита контекста**. Если функция читает историю или файл, ставьте `truncate_text`, чтобы не выжечь лимит токенов LLM огромной портянкой текста.
- [ ] **DRY & KISS**. Выносите общие функции (например парсинг URL) в `src/utils/`.