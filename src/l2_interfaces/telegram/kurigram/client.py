from pathlib import Path, PurePath
import sqlite3
from typing import Any

try:
    from pyrogram import Client
    from pyrogram.raw.functions.users import GetFullUser
    from pyrogram.raw.types import InputUserSelf
except ImportError:  # pragma: no cover - dependency is optional in tests/local tooling
    Client = None  # type: ignore[assignment]
    GetFullUser = None  # type: ignore[assignment]
    InputUserSelf = None  # type: ignore[assignment]

from src.utils.logger import system_logger
from src.l0_state.interfaces.state import KurigramState


def parse_telegram_api_id(api_id: int | str | None) -> int:
    """Return a Pyrogram-compatible numeric api_id with a clear config error."""
    if api_id is None or isinstance(api_id, bool):
        raise ValueError("TELETHON_API_ID должен быть положительным числом.")

    if isinstance(api_id, int):
        clean_api_id = api_id
    else:
        value = str(api_id).strip()
        if not value.isdecimal():
            raise ValueError("TELETHON_API_ID должен быть положительным числом.")
        clean_api_id = int(value)

    if clean_api_id <= 0:
        raise ValueError("TELETHON_API_ID должен быть положительным числом.")
    return clean_api_id


def validate_pyrogram_session_name(session_name: str | Path) -> str:
    """Validate a config-level Kurigram/Pyrogram session basename."""
    raw_name = str(session_name).strip()
    if raw_name.endswith(".session"):
        raw_name = raw_name[: -len(".session")]

    path = PurePath(raw_name)
    if (
        not raw_name
        or path.is_absolute()
        or len(path.parts) != 1
        or raw_name in {".", ".."}
    ):
        raise ValueError(
            "telegram.kurigram.session_name должен быть именем файла без пути."
        )

    return raw_name


def split_pyrogram_session_path(session_path: str | Path) -> tuple[str, str]:
    """
    Convert a stored Telegram User API session path into Pyrogram's name/workdir pair.
    """
    path = Path(session_path).expanduser()
    if path.suffix == ".session":
        path = path.with_suffix("")

    return validate_pyrogram_session_name(path.name), str(path.parent)


def _sqlite_tables(path: Path) -> set[str]:
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {name for (name,) in rows}


def _is_legacy_session(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False

    try:
        tables = _sqlite_tables(path)
    except sqlite3.DatabaseError:
        return False

    legacy_markers = {"entities", "sent_files", "update_state"}
    pyrogram_markers = {"version", "peers"}
    return bool(tables & legacy_markers) and not bool(tables & pyrogram_markers)


def ensure_pyrogram_session_compatible(session_name: str, workdir: str | Path) -> Path:
    session_name = validate_pyrogram_session_name(session_name)
    session_file = Path(workdir).expanduser() / f"{session_name}.session"
    if _is_legacy_session(session_file):
        raise RuntimeError(
            "Найден старый Telethon session-файл, который Kurigram/Pyrogram не может "
            "безопасно открыть. Переименуйте или удалите настроенный session-файл и пройдите "
            "авторизацию Telegram User API заново."
        )
    return session_file


class KurigramClient:
    """
    Управляет подключением к Telegram через User API.
    """

    def __init__(
        self,
        state: KurigramState,
        api_id: int | str,
        api_hash: str,
        session_path: str,
        timezone: int,
    ):
        self.state = state

        self.api_id = parse_telegram_api_id(api_id)
        self.api_hash = api_hash
        self.session_path = session_path
        self.session_name, self.workdir = split_pyrogram_session_path(session_path)
        self.timezone = timezone
        self._client: Any | None = None

    @staticmethod
    def _split_session_path(session_path: str) -> tuple[str, str]:
        return split_pyrogram_session_path(session_path)

    @staticmethod
    def _display_name(entity: Any) -> str:
        title = getattr(entity, "title", None)
        if title:
            return title

        parts = [
            getattr(entity, "first_name", None),
            getattr(entity, "last_name", None),
        ]
        name = " ".join(part for part in parts if part)
        if name:
            return name

        username = getattr(entity, "username", None)
        if username:
            return f"@{username}"

        entity_id = getattr(entity, "id", None)
        return f"ID {entity_id}" if entity_id is not None else "Unknown"

    @staticmethod
    def _pyrogram_channel_id(raw_channel_id: int) -> int:
        channel_id = str(raw_channel_id)
        if channel_id.startswith("-100"):
            return raw_channel_id
        return int(f"-100{channel_id.lstrip('-')}")

    def client(self) -> Any:
        """Безопасный доступ к инстансу Kurigram/Pyrogram."""
        if not self._client:
            raise RuntimeError("Telegram User API client не запущен.")
        return self._client

    async def start(self) -> None:
        """
        Запускает клиента.
        При первом запуске Kurigram/Pyrogram попросит номер, код и 2FA пароль в консоли.
        """
        system_logger.info("[Telegram Kurigram] Инициализация клиента через Kurigram.")

        if Client is None:
            raise RuntimeError(
                "Kurigram не установлен. Установите пакет `kurigram` для импорта `pyrogram`."
            )

        try:
            Path(self.workdir).mkdir(parents=True, exist_ok=True)
            ensure_pyrogram_session_compatible(self.session_name, self.workdir)
            self._client = Client(
                self.session_name,
                api_id=self.api_id,
                api_hash=self.api_hash,
                workdir=self.workdir,
            )

            await self._client.start()

            me = await self._client.get_me()
            name = self._display_name(me)

            await self.update_profile_state()

            system_logger.info(f"[Telegram Kurigram] Успешная авторизация как: {name}")
            self.state.is_online = True

        except Exception as e:
            self.state.is_online = False
            if self._client:
                try:
                    await self._client.stop()
                except Exception:
                    pass
            self._client = None
            system_logger.error(f"[Telegram Kurigram] Критическая ошибка при запуске: {e}")
            raise

    async def stop(self) -> None:
        """Корректно закрывает соединение."""
        if not self._client:
            return

        try:
            await self._client.stop()
            system_logger.info("[Telegram Kurigram] Клиент отключен.")
        except Exception as e:
            system_logger.warning(f"[Telegram Kurigram] Ошибка остановки клиента: {e}")
        finally:
            self.state.is_online = False
            self._client = None

    async def _get_profile_details(self, me: Any) -> tuple[str, str]:
        bio = "Пусто"
        channel_info = ""

        if GetFullUser is not None and InputUserSelf is not None:
            try:
                full_me = await self.client().invoke(GetFullUser(id=InputUserSelf()))
                full_user = getattr(full_me, "full_user", None)
                bio = getattr(full_user, "about", None) or bio

                personal_channel_id = getattr(full_user, "personal_channel_id", None)
                if personal_channel_id:
                    channel = next(
                        (
                            chat
                            for chat in getattr(full_me, "chats", [])
                            if getattr(chat, "id", None) == personal_channel_id
                        ),
                        None,
                    )

                    if channel is None:
                        try:
                            channel = await self.client().get_chat(
                                self._pyrogram_channel_id(personal_channel_id)
                            )
                        except Exception:
                            channel = None

                    if channel is not None:
                        channel_name = self._display_name(channel)
                        channel_username = getattr(channel, "username", None)
                        un_str = f" (@{channel_username})" if channel_username else ""
                        channel_info = (
                            f"\nЛичный канал: {channel_name}{un_str} "
                            f"(ID: {personal_channel_id})"
                        )
                    else:
                        channel_info = f"\nЛичный канал: ID {personal_channel_id}"

                return bio, channel_info
            except Exception as e:
                system_logger.warning(
                    f"[Telegram Kurigram] Raw profile details unavailable: {e}"
                )

        profile_chat = await self.client().get_chat(getattr(me, "id", "me"))
        bio = getattr(profile_chat, "bio", None) or bio
        return bio, channel_info

    async def update_profile_state(self) -> None:
        """Запрашивает актуальные данные аккаунта (имя, юзернейм, био, канал) и сохраняет в стейт."""
        if not self._client:
            return

        try:
            me = await self._client.get_me()
            name = self._display_name(me)
            username = (
                f"@{me.username}" if getattr(me, "username", None) else "Без @username"
            )
            bio, channel_info = await self._get_profile_details(me)

            self.state.account_info = (
                f"Профиль: {name} ({username}) | Био: {bio}{channel_info}\n---"
            )
        except Exception as e:
            system_logger.error(f"[Telegram Kurigram] Ошибка обновления профиля: {e}")
            self.state.account_info = "Профиль: Ошибка загрузки данных\n---"

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Возвращает отформатированный блок контекста для агента.
        """

        if not self.state.is_online:
            return "### TELEGRAM USER API [OFF]\nИнтерфейс отключен."

        return (
            f"### TELEGRAM USER API [ON] \n"
            f"Account info: {self.state.account_info}\n"
            f"{self.state.last_chats}"
        )
