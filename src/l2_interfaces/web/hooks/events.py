import json
import uuid
from aiohttp import web

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.dtime import get_now_formatted

from src.l0_state.interfaces.state import WebHooksState
from src.l2_interfaces.web.hooks.client import WebHooksClient


class WebHooksEvents:
    """
    Фоновый воркер: запускает aiohttp сервер для приема вебхуков.
    """

    def __init__(
        self, client: WebHooksClient, state: WebHooksState, event_bus: EventBus, timezone: int
    ):
        self.client = client
        self.state = state
        self.bus = event_bus
        self.timezone = timezone

        self.app = web.Application()

        # Универсальный эндпоинт-воронка
        self.app.router.add_post("/webhook/{source}", self.handle_webhook)
        self.app.router.add_get("/webhook/{source}", self.handle_webhook)  # На всякий случай

        self.runner = None

    async def start(self) -> None:
        """
        Запускает вебхук.
        """

        if self.state.is_online:
            return

        if not self.client.secret_token:
            system_logger.error(
                "[Web Hooks] WEBHOOK_SECRET не задан в .env. Сервер не запущен."
            )
            return

        try:
            self.runner = web.AppRunner(self.app, access_log=None)
            await self.runner.setup()
            site = web.TCPSite(self.runner, self.client.config.host, self.client.config.port)
            await site.start()

            self.state.is_online = True
            system_logger.info(
                f"[Web Hooks] Сервер запущен на http://{self.client.config.host}:{self.client.config.port}"
            )
            
        except Exception as e:
            system_logger.error(f"[Web Hooks] Ошибка запуска сервера: {e}")

            # Убираем за собой мусор, если бинд порта упал
            if self.runner:
                await self.runner.cleanup()
                self.runner = None

    async def stop(self) -> None:
        """
        Останавливает вебхук.
        """

        self.state.is_online = False
        if self.runner:
            await self.runner.cleanup()
            system_logger.info("[Web Hooks] Сервер остановлен.")

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        Обработчик входящих запросов.
        """

        # Валидация токена
        token = request.query.get("token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "").strip()

        if token != self.client.secret_token:
            system_logger.warning(
                f"[Web Hooks] Несанкционированная попытка доступа с IP {request.remote} (входящий токен невалиден)"
            )
            return web.json_response(
                {"status": "error", "message": "Unauthorized"}, status=401
            )

        # Получение данных
        source = request.match_info.get("source", "unknown")

        try:
            payload = await request.json()
            is_json = True
        except json.JSONDecodeError:
            payload = await request.text()
            is_json = False

        # Обновление стейта L0
        hook_id = str(uuid.uuid4())[:8]
        time_str = get_now_formatted(self.timezone, "%H:%M:%S")

        # Делаем короткое превью для промпта
        raw_str = json.dumps(payload, ensure_ascii=False) if is_json else str(payload)
        preview = raw_str.replace("\n", " ").strip()

        limit = self.client.config.preview_max_chars
        if len(preview) > limit:
            preview = preview[:limit] + "... [Обрезано]"

        self.state.add_hook(hook_id, source, time_str, payload, preview)
        system_logger.info(f"[Web Hooks] Принят вебхук от '{source}' (ID: {hook_id})")

        # Проброс события в ядро агента
        await self.bus.publish(
            Events.WEBHOOK_MESSAGE_INCOMING,
            source=source,
            hook_id=hook_id,
            message=f"Новый вебхук от {source}",
            preview=preview,
        )

        return web.json_response({"status": "ok", "id": hook_id})
