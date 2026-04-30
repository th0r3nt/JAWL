# Настройка RSS-лент (Web RSS)

Интерфейс Web RSS предназначен для автоматического отслеживания новостей, статей и релизов через форматы RSS и Atom.

## Механика работы
Интерфейс не требует от агента тратить токены на регулярные запросы.
1. Фоновый процесс опрашивает указанные ленты с частотой, заданной в `polling_interval_sec`.
2. Заголовки последних публикаций выводятся на приборную панель агента (L0 State) для поддержания общего контекста.
3. При обнаружении новой уникальной публикации система публикует системное событие `RSS_NEW_ENTRY` уровня `BACKGROUND`. 
4. Агент видит оповещение и, если тема публикации релевантна его задачам или интересам, может использовать навык `read_rss_feed` для извлечения полного текста статьи (очищенного от HTML-мусора).

## Примеры полезных лент

Ниже представлен список популярных источников, которые можно добавить в блок `feeds` файла `interfaces.yaml`:

**Технологии и IT:**
- Хабр (Все потоки): `https://habr.com/ru/rss/all/all/`
- Хабр (Искусственный интеллект): `https://habr.com/ru/rss/hub/artificial_intelligence/`
- TechCrunch: `https://techcrunch.com/feed/`

**Научные публикации (ArXiv):**
- Computer Science - AI: `https://export.arxiv.org/rss/cs.AI`
- Computer Science - Machine Learning: `https://export.arxiv.org/rss/cs.LG`

**Релизы GitHub-репозиториев:**
Для получения RSS-ленты релизов любого репозитория, добавьте `.atom` в конец URL страницы релизов:
- Релизы Python: `https://github.com/python/cpython/releases.atom`
- Релизы JAWL: `https://github.com/th0r3nt/JAWL/releases.atom`

**YouTube каналы:**
Для отслеживания видео достаточно знать ID канала:
- `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`