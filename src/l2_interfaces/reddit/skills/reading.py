from typing import Literal

from src.utils.logger import system_logger
from src.utils._tools import truncate_text
from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.reddit.client import RedditClient


class RedditReading:
    """
    Навыки для чтения Reddit.
    Поиск сабреддитов, чтение постов и комментариев.
    """

    def __init__(self, client: RedditClient):
        self.client = client

    @skill()
    async def search_subreddits(self, query: str, limit: int = 5) -> SkillResult:
        """Ищет релевантные сабреддиты по ключевому слову (например: 'singularity' или 'sysadmin')."""

        try:
            reddit = self.client.reddit()
            subreddits = []

            async for sub in reddit.subreddits.search(query, limit=limit):
                desc = truncate_text(sub.public_description or "Нет описания", 100, "...")
                subreddits.append(
                    f"- r/{sub.display_name} | Подписчиков: {sub.subscribers}\n  Описание: {desc}"
                )

            if not subreddits:
                return SkillResult.ok(f"По запросу '{query}' сабреддиты не найдены.")

            self.client.state.add_history(f"Поиск сабреддитов: '{query}'")
            system_logger.info(f"[Reddit] Выполнен поиск сабреддитов по '{query}'")

            return SkillResult.ok("\n\n".join(subreddits))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске сабреддитов: {e}")

    @skill()
    async def get_subreddit_posts(
        self, subreddit_name: str, sort_by: Literal["hot" "new" "top"] = "hot", limit: int = 5
    ) -> SkillResult:
        """
        Получает список постов из сабреддита.
        Возвращает ID постов для их дальнейшего чтения.
        """

        if sort_by not in ("hot", "new", "top"):
            return SkillResult.fail("Ошибка: sort_by должен быть 'hot', 'new' или 'top'.")

        try:
            reddit = self.client.reddit()
            sub = await reddit.subreddit(subreddit_name)

            if sort_by == "hot":
                iterator = sub.hot(limit=limit)
            elif sort_by == "new":
                iterator = sub.new(limit=limit)
            else:
                iterator = sub.top("week", limit=limit)

            posts = []
            async for post in iterator:
                posts.append(
                    f"[ID: `{post.id}`] {post.title}\n"
                    f"  ↳ Upvotes: {post.score} | Автор: {post.author} | Комментов: {post.num_comments}"
                )

            if not posts:
                return SkillResult.ok(f"Сабреддит r/{subreddit_name} пуст или не существует.")

            self.client.state.add_history(f"Просмотр r/{subreddit_name} ({sort_by})")
            system_logger.info(f"[Reddit] Запрошены посты из r/{subreddit_name}")

            return SkillResult.ok("\n\n".join(posts))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении постов: {e}")

    @skill()
    async def read_post(self, post_id: str) -> SkillResult:
        """
        Открывает пост по ID, читает его содержимое и топовые комментарии.
        """

        try:
            reddit = self.client.reddit()

            # Submission тянет пост по ID
            post = await reddit.submission(id=post_id)

            # Читаем комментарии. replace_more(limit=0) обрезает вложенные ветки,
            # оставляя только топовые комментарии (защита контекста агента)
            await post.comments.replace_more(limit=0)

            content = truncate_text(post.selftext or "[Текст отсутствует / Медиа-пост]", 2000)

            lines = [
                f"=== Пост: {post.title} ===",
                f"Сабреддит: r/{post.subreddit}",
                f"Автор: {post.author} | Upvotes: {post.score}",
                f"\nТекст поста:\n{content}\n",
                "=== Топовые комментарии ===",
            ]

            comments = post.comments[: self.client.config.read_limit]
            if not comments:
                lines.append("Комментариев нет.")

            else:
                for comment in comments:
                    c_text = truncate_text(comment.body, 500)
                    lines.append(f"[{comment.author} | +{comment.score}]: {c_text}\n---")

            self.client.state.add_history(f"Чтение поста ID: {post_id}")
            system_logger.info(f"[Reddit] Прочитан пост {post_id}")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении поста: {e}")
