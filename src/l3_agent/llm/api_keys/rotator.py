import os
import time
from dotenv import load_dotenv
from typing import List, Dict

from src.utils.logger import system_logger

load_dotenv()


class APIKeyRotator:
    """
    Ротатор API ключей для LLM.
    Отслеживает мертвые ключи и временные кулдауны (Rate Limits).
    """

    def __init__(self):
        self.keys: List[str] = self._load_keys()
        # Хранит timestamp, до которого ключ недоступен из-за Rate Limit
        self._cooldowns: Dict[str, float] = {k: 0.0 for k in self.keys}
        self._current_index: int = 0

    def _load_keys(self) -> List[str]:
        raw_keys = sorted(
            [
                (k, v)
                for k, v in os.environ.items()
                if k.startswith("LLM_API_KEY_") and v.strip()
            ]
        )
        keys = [v for k, v in raw_keys]

        if not keys:
            system_logger.error("[System] Не найдено ни одного ключа 'LLM_API_KEY_' в .env.")
            raise ValueError("LLM API keys not found. Check your .env file.")

        system_logger.info(f"[System] APIKeyRotator загрузил ключей: {len(keys)}.")
        return keys

    def get_next_key(self) -> str:
        if not self.keys:
            raise ValueError("Список API ключей пуст (или все были забанены).")

        now = time.time()
        attempts = len(self.keys)

        # Ищем первый доступный ключ не в кулдауне
        for _ in range(attempts):
            key = self.keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.keys)

            if self._cooldowns.get(key, 0.0) <= now:
                return key

        # Если дошли сюда - все ключи в кулдауне. Находим тот, который освободится раньше всех
        soonest_key = min(self.keys, key=lambda k: self._cooldowns.get(k, 0.0))
        wait_time = int(self._cooldowns[soonest_key] - now)
        raise RuntimeError(
            f"Все API ключи исчерпали лимиты. Необходимо подождать {wait_time} сек."
        )

    def ban_key(self, key: str):
        """Удаляет ключ из ротации навсегда (например, при HTTP 401)."""
        if key in self.keys:
            self.keys.remove(key)
            if key in self._cooldowns:
                del self._cooldowns[key]

            # Маскируем для логов (выводим только первые 6 символов)
            masked = key[:6] + "***" if len(key) > 6 else "***"
            system_logger.warning(f"[LLM] Ключ {masked} удален из пула (Dead, помянем).")

            if self.keys:
                self._current_index = self._current_index % len(self.keys)

    def cooldown_key(self, key: str, seconds: int = 60):
        """Временно блокирует ключ (например, при HTTP 429)."""
        if key in self.keys:
            self._cooldowns[key] = time.time() + seconds
            masked = key[:6] + "***" if len(key) > 6 else "***"
            system_logger.warning(
                f"[LLM] Ключ {masked} ушел в кулдаун на {seconds} сек (Rate Limit)."
            )

    def total_keys(self) -> int:
        return len(self.keys)
