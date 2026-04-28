import json
import uuid
import time
from pathlib import Path


def send_event(message: str, payload: dict = None):
    """
    Отправляет событие (Event) главному агенту JAWL.

    Важно: Вызов этой функции будит агента (прерывает его сон).
    Полезно для важных уведомлений,
    которые требуют немедленной реакции и действий.
    """
    if payload is None:
        payload = {}
    _write_event({"message": message, "payload": payload})


def update_dashboard(name: str, markdown_content: str):
    """
    Создает или обновляет кастомный блок в системном контексте (L0 State) агента.

    Эта функция пассивно обновляет контекст и не будит агента.
    Полезно для фоновых демонов.
    """
    payload = {
        "_jawl_internal_type": "dashboard_update",
        "name": name,
        "content": markdown_content,
    }
    _write_event({"message": f"Update dashboard {name}", "payload": payload})


def _write_event(data: dict):
    """Внутренняя функция для атомарной записи событий в IPC-директорию."""
    events_dir = Path(__file__).parent / ".jawl_events"
    events_dir.mkdir(parents=True, exist_ok=True)

    event_id = str(uuid.uuid4())
    temp_path = events_dir / f"{int(time.time())}_{event_id}.tmp"
    file_path = events_dir / f"{int(time.time())}_{event_id}.json"

    with open(temp_path, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False)

    temp_path.rename(file_path)


"""
=============================================================================
ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
=============================================================================

Пример: тихий дашборд
-----------------------------------------------------
import time
from framework_api import update_dashboard

def crypto_monitor():
    while True:
        # Представим, что здесь логика запроса к API биржи...
        btc_price = 65000
        
        content = f"**BTC**: ${btc_price}\\n_Updated: {time.ctime()}_"
        
        # Агент не проснется, но увидит эти цены в контексте на следующем тике
        update_dashboard("Crypto Market", content)
        
        time.sleep(300) # Ждем 5 минут

Пример: активный алерт
-----------------------------------------------------
import time
from framework_api import send_event

def server_watchdog():
    while True:
        # Представим, что мы пингуем сервер...
        server_is_down = True 
        
        if server_is_down:
            # Это событие моментально разбудит агента, чтобы он починил сервер
            send_event(
                message="Критическая ошибка: База данных недоступна.", 
                payload={"server": "db_main", "error": "Timeout"}
            )
            break # Выходим, чтобы не спамить ивентами каждую секунду
            
        time.sleep(60)
"""
