import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.settings import RedditConfig
from src.l0_state.interfaces.state import RedditState
from src.l2_interfaces.reddit.client import RedditClient
from src.l2_interfaces.reddit.skills.reading import RedditReading

# ===================================================================
# HELPERS
# ===================================================================


async def async_generator(items):
    """Хелпер для имитации асинхронных генераторов AsyncPRAW."""
    for item in items:
        yield item


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def reddit_config():
    return RedditConfig(enabled=True, agent_account=False, read_limit=2)


@pytest.fixture
def reddit_state():
    return RedditState(history_limit=5)


@pytest.fixture
def reddit_client(reddit_config, reddit_state):
    client = RedditClient(
        config=reddit_config,
        state=reddit_state,
        client_id="fake_id",
        client_secret="fake_secret",
    )
    # Создаем мок для самого инстанса asyncpraw.Reddit
    client._reddit = AsyncMock()
    return client


@pytest.fixture
def reading_skills(reddit_client):
    return RedditReading(client=reddit_client)


# ===================================================================
# TESTS: CLIENT & STATE
# ===================================================================


@pytest.mark.asyncio
@patch("src.l2_interfaces.reddit.client.asyncpraw.Reddit")
async def test_client_start_stop(mock_asyncpraw, reddit_config, reddit_state):
    """Тест: успешная инициализация и остановка клиента."""
    mock_instance = AsyncMock()
    mock_instance.read_only = True
    mock_asyncpraw.return_value = mock_instance

    client = RedditClient(
        config=reddit_config, state=reddit_state, client_id="id", client_secret="secret"
    )

    await client.start()
    assert client.state.is_online is True

    await client.stop()
    assert client.state.is_online is False
    mock_instance.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_reddit_state_mru(reddit_state):
    """Тест: история активности (MRU кэш) соблюдает лимиты."""
    for i in range(7):
        reddit_state.add_history(f"Action {i}")

    # Лимит = 5, значит старые (0 и 1) должны быть удалены
    assert len(reddit_state.history) == 5
    assert "Action 6" in reddit_state.recent_activity
    assert "Action 0" not in reddit_state.recent_activity


# ===================================================================
# TESTS: READING SKILLS
# ===================================================================


@pytest.mark.asyncio
async def test_search_subreddits(reading_skills, reddit_client):
    """Тест: поиск сабреддитов корректно парсит данные."""

    mock_sub = MagicMock()
    mock_sub.display_name = "Python"
    mock_sub.subscribers = 1000000
    mock_sub.public_description = "A community for Python."

    # Заменяем на MagicMock, чтобы .search() возвращал генератор синхронно, а не как корутину
    reddit_client.reddit().subreddits.search = MagicMock(
        return_value=async_generator([mock_sub])
    )

    res = await reading_skills.search_subreddits("python", limit=1)

    assert res.is_success is True
    assert "r/Python" in res.message
    assert "1000000" in res.message
    assert "A community for Python." in res.message
    assert "Поиск сабреддитов" in reddit_client.state.recent_activity


@pytest.mark.asyncio
async def test_get_subreddit_posts(reading_skills, reddit_client):
    """Тест: получение списка постов из сабреддита."""

    mock_post = MagicMock()
    mock_post.id = "post123"
    mock_post.title = "How to write tests?"
    mock_post.score = 42
    mock_post.author = "TestUser"
    mock_post.num_comments = 5

    mock_subreddit = AsyncMock()
    # .hot() вызывается синхронно, поэтому используем MagicMock, возвращающий асинхронный генератор
    mock_subreddit.hot = MagicMock(return_value=async_generator([mock_post]))
    reddit_client.reddit().subreddit.return_value = mock_subreddit

    res = await reading_skills.get_subreddit_posts("programming", sort_by="hot", limit=1)

    assert res.is_success is True
    assert "post123" in res.message
    assert "How to write tests?" in res.message
    assert "42" in res.message
    assert "TestUser" in res.message
    assert "Просмотр r/programming (hot)" in reddit_client.state.recent_activity


@pytest.mark.asyncio
async def test_read_post(reading_skills, reddit_client):
    """Тест: глубокое чтение поста и его комментариев."""

    mock_comment = MagicMock()
    mock_comment.author = "Expert"
    mock_comment.score = 10
    mock_comment.body = "Just use Pytest."

    mock_post = AsyncMock()
    mock_post.title = "Help me"
    mock_post.subreddit = "Python"
    mock_post.author = "Noob"
    mock_post.score = 5
    mock_post.selftext = "I need help with testing."

    # Создаем правильный мок для CommentForest
    mock_comments_forest = MagicMock()
    mock_comments_forest.replace_more = AsyncMock()
    # Имитируем поведение среза: post.comments[:limit] должен вернуть наш список
    mock_comments_forest.__getitem__.return_value = [mock_comment]

    mock_post.comments = mock_comments_forest

    reddit_client.reddit().submission.return_value = mock_post

    res = await reading_skills.read_post("post123")

    assert res.is_success is True
    # Проверка тела поста
    assert "Help me" in res.message
    assert "I need help with testing." in res.message
    # Проверка комментариев
    assert "Expert" in res.message
    assert "+10" in res.message
    assert "Just use Pytest." in res.message

    mock_comments_forest.replace_more.assert_awaited_once_with(limit=0)
