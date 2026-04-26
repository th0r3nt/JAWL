# 🔌 Интерфейсы (L2) в JAWL: Руководство пользователя и разработчика

Слой **L2 (Interfaces)** - это органы чувств и руки агента. Через интерфейсы агент читает файлы, отправляет сообщения, делает коммиты и сёрфит интернет. 

Этот документ разделен на две части: для **пользователей** (как настроить готовое) и для **разработчиков** (как написать свой интерфейс, не сломав архитектуру).

---

## 🛠 Часть 1. Для пользователей (Как включить и настроить)

Все интерфейсы по умолчанию выключены, чтобы агент не лез туда, куда его не просили. 

### 1. Включение через CLI (Рекомендуется)
Самый простой способ управлять интерфейсами - запустить скрипт `jawl.py` и в главном меню выбрать:
👉 **"⚙️ Мастер настройки интерфейсов"**
Там можно включать и выключать модули пробелом/энтером. Изменения автоматически запишутся в файл `config/interfaces.yaml`.

### 2. Ключи и авторизация (.env)
Некоторым интерфейсам для работы нужны ключи API или пароли. Их нужно прописать в файле `.env` (создайте его из `.env.example`, если его еще нет).
- **Telegram User API (Kurigram)**: Включается через `telegram.kurigram` в `config/interfaces.yaml`. Нужны `TELETHON_API_ID` и `TELETHON_API_HASH` (берутся на my.telegram.org); это legacy env-имена, сохраненные для совместимости со старыми установками. Новая сессия хранится в `src/utils/local/data/kurigram/`; существующие Kurigram/Pyrogram-сессии из прежнего `src/utils/local/data/telethon/` подхватываются, если новой сессии еще нет. Старые `.session` от Telethon нельзя безопасно переиспользовать, поэтому при переходе их нужно переименовать или удалить и пройти авторизацию заново. Legacy config key `telegram.telethon` все еще читается, но для новых конфигов используйте `telegram.kurigram`.
- **Telegram (Aiogram)**: Нужен `AIOGRAM_BOT_TOKEN` от @BotFather.
- **GitHub**: Нужен классический `GITHUB_TOKEN` (PAT) с правами `repo` и `read:user`.
- **Email**: Нужен логин и **специальный Пароль приложения (App Password)**. Обычный пароль от почты не подойдет - Google/Yandex заблокируют вход.

### 3. Ручная настройка (interfaces.yaml)
Для тонкой настройки (лимиты, таймауты, права доступа) откройте `config/interfaces.yaml`. 
*Самый важный параметр - `access_level` в `host_os`*. Он определяет, может ли агент стереть к чертям вам жесткий диск или он заперт в папке `sandbox/`.

---

## 🏗 Часть 2. Для разработчиков (Как создать свой интерфейс)

Мы строго соблюдаем **SOLID** и изоляцию слоев. Агент (L3) ничего не знает о библиотеках (L2). Он общается с интерфейсом только через зарегистрированные навыки (Skills) и видит его статус через приборную панель (L0 State).

Создание нового интерфейса (например, `Discord`) всегда состоит из 5 шагов.

### Шаг 1. Создание стейта (L0)
Откройте файл `src/l0_state/interfaces/state.py` и добавьте класс-хранилище.
**Правило:** Стейт должен быть пассивным. Никаких I/O операций. Только кэш данных.

```python
class DiscordState:
    def __init__(self, recent_limit: int = 10):
        self.is_online = False
        self.last_messages = "Пусто." # Будет хранить последние сообщения с интерфейса
```

Добавьте его инициализацию в `src/main.py` внутри метода `setup_l0_state()`.

### Шаг 2. Структура папок (L2)
Создайте папку в `src/l2_interfaces/discord/` со следующей структурой:
```text
discord/
├── skills/
│   ├── __init__.py
│   └── messages.py     # Навыки (руки агента)
├── __init__.py
├── bootstrap.py        # Инициализатор
├── client.py           # Менеджер соединения
└── events.py           # Фоновые слушатели и поллинг (уши агента)
```

### Шаг 3. Написание Клиента (`client.py`)
Клиент инкапсулирует подключение к API и хранит ссылку на стейт (L0). 
Обязательный метод - `get_context_block`. Это то, что агент будет "видеть" в своем системном промпте на каждом тике.

```python
from src.l0_state.interfaces.state import DiscordState

class DiscordClient:
    def __init__(self, state: DiscordState, token: str):
        self.state = state
        self.token = token
        self.state.is_online = True

    async def get_context_block(self, **kwargs) -> str:
        if not self.state.is_online:
            return "### DISCORD [OFF]\nИнтерфейс отключен."
        return f"### DISCORD [ON]\nПоследние сообщения:\n{self.state.last_messages}"
```

### Шаг 4. Написание Навыков (`skills/messages.py`)
Навыки - это то, что агент может вызывать. 
**Правило:** Навыки должны возвращать объект `SkillResult`. Все методы для агента помечаются декоратором `@skill()` - также рекомендуется писать подробные докстринги навыков для агента.

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
            return SkillResult.ok(f"Сообщение отправлено в канал {channel_id}.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка отправки: {e}")
```

### Шаг 5. Сборка и Регистрация (`bootstrap.py` и `initializer.py`)
В `bootstrap.py` мы связываем всё воедино и отдаем системе.

```python
from typing import List, Any
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

def setup_discord(system, token: str) -> List[Any]:
    client = DiscordClient(state=system.discord_state, token=token)
    
    # 1. Даем агенту "руки"
    register_instance(DiscordMessages(client))
    
    # 2. Даем агенту "глаза" (Контекст)
    system.context_registry.register_provider(
        name="discord", 
        provider_func=client.get_context_block, 
        section=ContextSection.INTERFACES
    )
    
    # 3. Возвращаем компоненты жизненного цикла (если у клиента есть start/stop)
    return [client]
```

Осталось только вызвать `setup_discord` внутри `src/l2_interfaces/initializer.py`.

### 📌 Чек-лист хорошего интерфейса:
- [ ] **Никакого хардкода токенов**. Всё берется из `.env` и прокидывается через параметры.
- [ ] **Защита контекста**. Если функция читает историю или файл, ставьте `truncate_text`, чтобы не выжечь лимит токенов LLM огромной портянкой текста.
- [ ] **DRY & KISS**. Выносите общие функции (например парсинг URL) в `src/utils/`.
```
