import pytest
import asyncio
from src.utils.event.bus import EventBus
from src.utils.event.registry import EventConfig, EventLevel

# ===================================================================
# FIXTURES
# ===================================================================

TEST_EVENT = EventConfig(
    name="TEST_EVENT", description="Тестовое событие", level=EventLevel.INFO
)


@pytest.fixture
def bus():
    return EventBus()


async def wait_for_bus(bus: EventBus):
    """
    Хелпер для тестов.
    Так как publish запускает обработчики в фоне (fire-and-forget),
    нам нужно дождаться их выполнения, чтобы проверить результат.
    """
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)


# ===================================================================
# TESTS
# ===================================================================


def test_subscribe_unsubscribe(bus):
    def dummy_handler():
        pass

    bus.subscribe(TEST_EVENT, dummy_handler)
    assert TEST_EVENT.name in bus.listeners
    assert dummy_handler in bus.listeners[TEST_EVENT.name]

    bus.unsubscribe(TEST_EVENT, dummy_handler)
    assert dummy_handler not in bus.listeners[TEST_EVENT.name]


@pytest.mark.asyncio
async def test_publish_sync_and_async(bus):
    results = []

    def sync_handler(data):
        results.append(f"sync_{data}")

    async def async_handler(data):
        await asyncio.sleep(0.01)
        results.append(f"async_{data}")

    bus.subscribe(TEST_EVENT, sync_handler)
    bus.subscribe(TEST_EVENT, async_handler)

    await bus.publish(TEST_EVENT, "hello")
    await wait_for_bus(bus)

    assert len(results) == 2
    assert "sync_hello" in results
    assert "async_hello" in results


@pytest.mark.asyncio
async def test_publish_with_exceptions(bus):
    results = []

    def bad_handler():
        raise ValueError("Специальная ошибка")

    def good_handler():
        results.append("ok")

    bus.subscribe(TEST_EVENT, bad_handler)
    bus.subscribe(TEST_EVENT, good_handler)

    await bus.publish(TEST_EVENT)
    await wait_for_bus(bus)

    assert len(results) == 1
    assert results[0] == "ok"


@pytest.mark.asyncio
async def test_publish_empty_event(bus):
    # Создаем событие, на которое нет подписок
    EMPTY_EVENT = EventConfig(
        name="NOBODY_LISTENS", description="Empty", level=EventLevel.INFO
    )
    await bus.publish(EMPTY_EVENT)
    assert len(bus.background_tasks) == 0
