from src.l0_state.interfaces.web.hooks_state import WebHooksState
from src.utils.settings import WebHooksConfig


class WebHooksClient:
    """
    Stateful клиент для интерфейса вебхуков.
    Хранит настройки и отдает контекстный блок.
    Сам HTTP сервер поднимется в модуле Events.
    """

    def __init__(self, state: WebHooksState, config: WebHooksConfig, secret_token: str):
        self.state = state
        self.config = config
        self.secret_token = secret_token

        self.state.host = config.host
        self.state.port = config.port

    async def get_context_block(self, **kwargs) -> str:
        if not self.state.is_online:
            return "### WEB HOOKS [OFF]\nИнтерфейс отключен."

        hooks_str = (
            "\n".join(self.state.preview_lines)
            if self.state.preview_lines
            else "  Пока пусто."
        )

        return (f"""
### WEB HOOKS [ON]
* Сервер: http://{self.state.host}:{self.state.port}

* Эндпоинт для входящих запросов: POST /webhook/{{source}} (где {{source}} - название сервиса-отправителя)
* Авторизация: параметр '?token=' или HTTP-заголовок 'Authorization: Bearer '

* Последние вебхуки:
{hooks_str}
""")