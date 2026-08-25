# -*- coding: utf-8 -*-
"""
Согласованность статики с бэкендом.

Фронтенд и сервер связаны атрибутом `data-cfg`. Разъехаться они могут молча:
поле останется на экране, но перестанет читаться и записываться. Эти тесты
ловят такое до запуска.
"""

import re

import pytest

from src.web import schema

CFG_RE = re.compile(r'data-cfg="([^"]+)"')
# button — бейдж «вкл/выкл» в шапке карточки интерфейса
CONTROL_RE = re.compile(r'<(?:input|select|span|button)\b[^>]*\bdata-cfg="[^"]*"[^>]*>')


def _cfg_keys(html):
    return CFG_RE.findall(html)


def _known_keys():
    """Три источника: settings.yaml, interfaces.yaml и .env."""
    return (set(schema.SETTINGS_FIELDS) | set(schema.INTERFACES_FIELDS)
            | set(schema.ENV_FIELDS))


# ---------------------------------------------------------------- привязка

def test_every_schema_key_is_present_in_markup(index_html):
    """Поле описано в схеме, но его нет на экране — значит, его нельзя изменить."""
    known = _known_keys()
    missing = sorted(known - set(_cfg_keys(index_html)))
    assert not missing, "нет контролов для: %s" % missing


def test_every_markup_key_is_known_to_backend(index_html):
    """Обратное: контрол есть, а сервер про него не знает — правки уйдут в никуда."""
    known = _known_keys()
    unknown = sorted(set(_cfg_keys(index_html)) - known)
    assert not unknown, "сервер не знает: %s" % unknown


def test_no_duplicate_bindings(index_html):
    """Один ключ на один контрол, иначе значения будут перетирать друг друга."""
    keys = _cfg_keys(index_html)
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, "привязаны дважды: %s" % dupes


def test_bound_controls_are_locked_until_load(index_html):
    """
    До ответа сервера поля заблокированы: иначе пользователь правит пустоту,
    а нажатие «Применить» записало бы её в файл.
    """
    unlocked = [tag for tag in CONTROL_RE.findall(index_html)
                if "disabled" not in tag]
    assert not unlocked, "не заблокировано: %s" % [t[:90] for t in unlocked]


def test_bound_controls_carry_no_values(index_html):
    """Выдуманных значений в разметке быть не должно — их подставляет сервер."""
    dirty = [tag for tag in CONTROL_RE.findall(index_html)
             if re.search(r'\bvalue="[^"]+"', tag)]
    assert not dirty, "значения зашиты в разметку: %s" % [t[:90] for t in dirty]


# ---------------------------------------------------------------- удалённое

def _settings_panel(html):
    return html[html.index('data-panel="settings"'):html.index('data-panel="interfaces"')]


@pytest.mark.parametrize("phrase", [
    "WEB_RESEARCHER",          # роли субагентов задаются декораторами в коде
    "V.E.G.A.",                # демо-имя агента
    "дерево мыслей 0.72",      # выдуманные оценки выгоды из прежнего макета
])
def test_fabricated_content_is_gone(index_html, phrase):
    """То, чему нет соответствия в конфиге, не должно вернуться при правках."""
    assert phrase not in _settings_panel(index_html), "снова появилось: %s" % phrase


def test_simulation_card_is_gone(index_html):
    """
    Карточка «Последняя симуляция» убрана: данных для неё нет, а пустая рамка
    на экране обещает то, чего не будет.
    """
    assert "Последняя симуляция" not in index_html
    assert 'data-demo="tot"' not in index_html


def test_drive_meters_carry_no_baked_in_values(index_html):
    """
    Дефицит и полоски теперь приходят из таблицы drives. В разметке они должны
    быть пустыми: зашитое значение показалось бы настоящим до первого ответа
    сервера.
    """
    panel = _settings_panel(index_html)

    assert 'data-demo="deficit"' not in panel, "остались демо-пометки дефицита"
    assert "дефицит 78" not in panel and "дефицит 34" not in panel

    for bar in re.findall(r'<div class="meter"><i[^>]*>', panel):
        assert 'width:0%' in bar, "в полоску зашита ненулевая ширина: %s" % bar


def test_remaining_placeholders_are_marked(index_html):
    """
    Не подключённые к данным места обязаны нести data-demo — иначе выдумку
    не отличить от настоящих значений. Осталось одно такое место: счётчики
    навыков на карточках интерфейсов.
    """
    kinds = set(re.findall(r'data-demo="(\w+)"', index_html))
    assert kinds == {"skills"}, "изменился состав заглушек: %s" % sorted(kinds)


# ---------------------------------------------------------------- эмбеддинги

def test_embedding_options_match_documentation(index_html):
    """
    Список моделей и рекомендованные пары «размерность / порог» берутся из
    docs/yaml/settings/vector_db.md. Разъедутся — пользователь получит
    несовместимую размерность и неработающую векторную базу.
    """
    from src.web import config_io as cio

    doc = (cio.ROOT_DIR / "docs" / "yaml" / "settings" / "vector_db.md").read_text(encoding="utf-8")
    documented = set(re.findall(r'`([\w.-]+/[\w.-]+)`', doc))

    select = re.search(r'<select[^>]*id="embModel".*?</select>', index_html, re.S).group(0)
    offered = set(re.findall(r'<option value="([^"]+)"', select))

    assert offered <= documented, "нет в документации: %s" % sorted(offered - documented)
    assert len(offered) == 3, "в документации три рекомендованные модели"


def test_embedding_presets_match_documentation(console_js):
    """Пары «модель → размерность, порог» должны совпадать с документацией."""
    from src.web import config_io as cio

    doc = (cio.ROOT_DIR / "docs" / "yaml" / "settings" / "vector_db.md").read_text(encoding="utf-8")
    block = re.search(r'var EMBEDDINGS = \{(.*?)\n  \};', console_js, re.S).group(1)

    for model, size, thr in re.findall(
            r'"([^"]+)":\s*\{size:\s*(\d+),\s*threshold:\s*([\d.]+)', block):
        section = doc[doc.index(model):]
        section = section[:section.find("\n1.") + 1 or len(section)]
        assert "`vector_size`): %s" % size in section, "%s: размерность %s" % (model, size)
        assert "`%s`" % thr in section, "%s: порог %s" % (model, thr)


# ---------------------------------------------------------------- целостность

def test_div_tags_are_balanced(index_html):
    assert index_html.count("<div") == index_html.count("</div>")


def test_no_inline_style_or_script_blocks(index_html):
    """Оформление и поведение живут в отдельных файлах."""
    assert "<style>" not in index_html
    assert re.search(r'<script>(?!\s*</script>)', index_html) is None


def test_js_ids_exist_in_markup(index_html, console_js):
    """getElementById по несуществующему id — тихая поломка."""
    ids = set(re.findall(r'\bid="([\w-]+)"', index_html))
    used = set(re.findall(r'getElementById\("([\w-]+)"\)', console_js))
    assert not (used - ids), "нет в разметке: %s" % sorted(used - ids)


def test_css_classes_are_used(index_html, console_js, styles_css):
    """Мёртвые правила накапливаются незаметно; классы может вешать и скрипт."""
    haystack = index_html + console_js
    declared = set(re.findall(r'\.([a-z][a-z0-9-]{2,})(?=[\s,{:.>\[])', styles_css))
    dead = sorted(c for c in declared if c not in haystack)
    assert not dead, "мёртвые классы: %s" % dead


# ---------------------------------------------------------------- панель сохранения

def test_late_snapshots_are_scoped(console_js):
    """
    Снимок значений для панели «Не сохранено» делается несколько раз: сразу,
    после ответа /api/config и после /api/drives. Поздний снимок без границ
    перезаписывал бы уже сделанную правку — панель просто не появлялась.
    Поэтому такие вызовы обязаны ограничивать себя своими полями.
    """
    calls = re.findall(r'\bcapture\((.*?)\)', console_js)
    calls = [c.strip() for c in calls if "function" not in c]

    scoped = [c for c in calls if c]
    bare = [c for c in calls if not c]

    assert '"[data-cfg]"' in scoped, "снимок после чтения конфигурации не ограничен"
    assert '"[data-drive]"' in scoped, "снимок после чтения мотиваторов не ограничен"
    assert len(bare) == 2, (
        "полный снимок допустим только при старте и после сохранения, "
        "найдено %d вызовов" % len(bare))


def test_drive_edits_are_attributed_to_the_database(console_js):
    """Правка своего мотиватора идёт в SQLite, а не в settings.yaml."""
    block = re.search(r'function fileOf\(el\)\{(.*?)\n  \}', console_js, re.S).group(1)
    assert "data-drive" in block, "источник правки мотиватора не различается"
    assert "мотиватор" in block.lower()


def test_drive_inputs_trigger_the_savebar(console_js):
    """Поля мотиваторов не имеют data-cfg — их надо ловить отдельно."""
    for event in ("input", "change"):
        handlers = re.findall(
            r'document\.addEventListener\("%s",\s*function\(e\)\{(.*?)\n  \}\);' % event,
            console_js, re.S)
        assert any('data-drive' in h for h in handlers), \
            "событие %s у полей мотиватора не поднимает панель" % event


# ---------------------------------------------------------------- шапка такта

def _header(html):
    return html[html.index('<div class="pulse">'):html.index('data-panel="settings"')]


def test_header_carries_no_invented_readings(index_html):
    """
    Раньше шапка крутила выдуманный цикл: обратный отсчёт с 47 секунд и «3 / 15»
    шагов. Значения приходят из /api/tick, в разметке должны быть прочерки.
    """
    header = _header(index_html)

    for element in ("wakeIn", "reactStep"):
        value = re.search(r'id="%s"[^>]*>([^<]*)<' % element, header).group(1).strip()
        assert value in ("", "—"), "%s показывает выдуманное «%s»" % (element, value)

    assert not re.search(r'\d+\s*/\s*\d+', header), "в шапке остался придуманный счёт шагов"


def test_header_has_a_slot_for_current_activity(index_html):
    """Чем агент занят прямо сейчас — отдельная строка, скрытая до первого ответа."""
    header = _header(index_html)
    slot = re.search(r'<span class="pulse-act"[^>]*>', header)

    assert slot, "нет места под текущее действие"
    assert "hidden" in slot.group(0), "строка действия должна быть скрыта до данных"


def test_tick_simulation_is_gone(console_js):
    """Случайные приоритеты и таймер-имитация такта не должны вернуться."""
    assert "PRIOS" not in console_js, "вернулись случайные приоритеты событий"
    assert "subscribeHeartbeat" not in console_js, "осталась заглушка потока такта"
    assert "/api/tick" in console_js, "шапка не запрашивает состояние такта"


def test_beats_are_queued_not_overwritten(console_js):
    """
    За один опрос может прийти несколько событий. Если удар просто заменяет
    очередь, из пачки будет виден только последний всплеск.
    """
    body = re.search(r'function pushBeat\(amp\)\{(.*?)\n  \}', console_js, re.S).group(1)
    assert "concat" in body, "удары перетирают друг друга вместо очереди"


def test_countdown_has_a_single_render_path(console_js):
    """
    Остаток до пробуждения сервер отдаёт относительным числом. Пока его рисовали
    из двух мест, повторная отрисовка устаревшим состоянием отматывала таймер
    назад: 08:16 → 08:15 → 08:18. Форматирование должно жить в одном месте.
    """
    uses = re.findall(r'fmtLeft\(', console_js)
    assert len(uses) == 2, "fmtLeft вызывается вне единой точки отрисовки"

    body = re.search(r'function paintWake\(\)\{(.*?)\n  \}', console_js, re.S)
    assert body and "fmtLeft(" in body.group(1), "нет единой точки отрисовки остатка"
    assert "wakeDeadline" in body.group(1), "остаток считается не от дедлайна"


def test_countdown_anchors_on_receipt_time(console_js):
    """Дедлайн строится от момента получения ответа, иначе он «омолаживается»."""
    assignment = re.search(r'wakeDeadline = t\.wakeInSec == null(.*?);', console_js, re.S)
    assert assignment, "дедлайн назначается не из состояния такта"
    assert "receivedAt" in assignment.group(1), "дедлайн привязан к «сейчас», а не к ответу"
    assert "res.receivedAt = Date.now()" in console_js, "момент получения не запоминается"


def test_first_answer_does_not_replay_old_beats(console_js):
    """
    Сервер помнит последние всплески, чтобы клиент не терял их между опросами.
    Но свежезагруженная страница увидит их все сразу — и пульс выдаст залп
    ударов, которых пользователь не застал. Первый ответ должен только
    догонять счётчик.
    """
    body = re.search(r'function paintTick\(t\)\{(.*?)\n    if \(t\.phase',
                     console_js, re.S).group(1)
    assert "beatsPrimed" in body, "первый ответ отрисовывает накопленные всплески"
    assert re.search(r'tickSeq = t\.seq', body), "счётчик всплесков не догоняется"


def test_passed_deadline_is_not_shown_as_zero(console_js):
    """
    Пока вкладка скрыта, опроса нет, и местный отсчёт добегает до нуля. Замереть
    на «00:00» — значит утверждать, что агент спит ровно ноль секунд, тогда как
    он в это время уже работает.
    """
    body = re.search(r'function paintWake\(\)\{(.*?)\n  \}', console_js, re.S).group(1)
    assert re.search(r'left <= 0', body), "истёкший срок не отличается от обычного"
    assert "visibilitychange" in console_js, "возврат на вкладку не обновляет состояние"


# ---------------------------------------------------------------- чат

def test_chat_has_no_invented_conversation(index_html):
    """Диалог из макета — выдумка. Переписку присылает агент."""
    chat = index_html[index_html.index('data-panel="chat"'):index_html.index('data-panel="db"')]

    assert "V.E.G.A." not in chat, "вернулся демо-агент"
    assert "CI по ветке dev" not in chat, "вернулась выдуманная переписка"
    assert chat.count('class="msg') == 0, "реплики зашиты в разметку"
    assert 'id="chatEmpty"' in chat, "нет заглушки на время загрузки"


def test_chat_composer_is_locked_until_connected(index_html):
    """
    До ответа сервера неизвестно, поднят ли терминал агента. Разрешать ввод
    значило бы обещать доставку, которой не будет.
    """
    chat = index_html[index_html.index('data-panel="chat"'):index_html.index('data-panel="db"')]

    for element in ("chatInput", "chatSend"):
        tag = re.search(r'<(?:textarea|button)[^>]*id="%s"[^>]*>' % element, chat).group(0)
        assert "disabled" in tag, "%s доступен до проверки связи" % element


def test_chat_does_not_replay_history_from_the_stream(console_js):
    """
    История из файла и буфер потока перекрываются: агент пишет в файл те же
    реплики, что рассылает подписчикам. Без догоняющего счётчика каждая реплика
    показывалась бы дважды.
    """
    body = re.search(r'function loadChat\(\)\{(.*?)\n  \}', console_js, re.S).group(1)
    assert re.search(r'chatSeq = res\.status\.seq', body), "счётчик потока не догоняется"


def test_chat_subscription_ignores_tab_visibility(console_js):
    """
    Свёрнутое окно браузера — не «оператор ушёл». Иначе каждый переход на
    соседнюю вкладку слал бы агенту «терминал закрыт» и «терминал открыт»,
    а открытие ещё и ускоряет ему пробуждение.
    """
    body = re.search(r'function syncChatSubscription\(\)\{(.*?)\n  \}',
                     console_js, re.S).group(1)
    assert "visibilityState" not in body, "подписка гаснет при сворачивании окна"
    assert "panel-hidden" in body, "подписка не привязана к разделу «Чат»"


def test_chat_explains_a_disabled_terminal(console_js):
    """
    Весь чат держится на интерфейсе «Терминал». Выключен — пользователь должен
    прочитать об этом, а не получить отказ сокета вроде «[WinError 1225]».
    """
    assert "terminalEnabled" in console_js, "флаг интерфейса не учитывается"

    text = re.search(r'var TERMINAL_OFF =\s*(.*?);', console_js, re.S).group(1)
    assert "Терминал" in text and "перезапустите" in text, \
        "объяснение не называет ни настройку, ни необходимость перезапуска"

    body = re.search(r'function applyChatStatus\(status\)\{(.*?)\n  \}',
                     console_js, re.S).group(1)
    assert "TERMINAL_OFF" in body, "объяснение не показывается"
    assert re.search(r'disabled\s*=\s*status\.terminalEnabled === false', body), \
        "причина «выключено» не отделена от состояния соединения"


def test_chat_offers_a_way_to_the_setting(console_js):
    """
    Искать нужный выключатель среди восемнадцати карточек интерфейсов вручную —
    занятие на минуту. Из чата должна вести кнопка.
    """
    body = re.search(r'function chatJumpButton\(\)\{(.*?)\n  \}', console_js, re.S).group(1)

    assert 'data-tab="interfaces"' in body, "кнопка не переключает раздел"
    assert 'revealInterface("host.terminal.enabled")' in body, \
        "кнопка не открывает саму настройку"


def test_reveal_interface_resets_filters(console_js):
    """Карточка может быть скрыта фильтром или поиском — иначе переход впустую."""
    body = re.search(r'function revealInterface\(path\)\{(.*?)\n  \}',
                     console_js, re.S).group(1)

    assert "ifcSearch" in body, "поиск не сбрасывается"
    assert 'data-ifc="all"' in body, "фильтр не сбрасывается"
    assert "selectIfc" in body, "карточка не выбирается"


def test_terminal_toggle_is_where_the_chat_points(index_html):
    """Кнопка ведёт к конкретному контролу — он обязан существовать."""
    assert 'data-cfg="interfaces:host.terminal.enabled"' in index_html


# ---------------------------------------------------------------- версия и мотиваторы

def test_version_is_not_hardcoded_in_markup(index_html):
    """
    Версия в углу раньше была зашита числом и разошлась с настоящей на три
    минорных выпуска. Теперь её подставляет сервер.
    """
    tag = re.search(r'<span class="brand-ver"[^>]*>([^<]*)</span>', index_html)

    assert tag, "место под версию исчезло"
    assert not tag.group(1).strip(), "версия зашита в разметку: %r" % tag.group(1)
    assert 'id="brandVer"' in tag.group(0), "серверу некуда её положить"


def test_version_is_taken_from_the_config_response(console_js):
    body = re.search(r'function applyVersion\(version\)\{(.*?)\n  \}',
                     console_js, re.S).group(1)

    assert "brandVer" in body
    assert "applyVersion(cfg.version)" in console_js, "версия не применяется при загрузке"


def test_every_drive_card_has_room_for_a_description(index_html):
    """
    Описания были только у своих мотиваторов: у фундаментальных не было даже
    места под текст, и карточки выглядели недоделанными.
    """
    panel = _settings_panel(index_html)
    cards = re.findall(r'<div class="drive"[^>]*data-key="\w+".*?</div>\s*</div>',
                       panel, re.S)

    assert len(cards) == 3, "ожидалось три фундаментальных мотиватора, нашлось %d" % len(cards)
    for card in cards:
        assert 'class="hint dsc"' in card, "в карточке нет места под описание"


def test_drives_header_has_no_table_name(index_html):
    """«таблица drives» — подробность реализации, пользователю она ни о чём."""
    panel = _settings_panel(index_html)
    header = re.search(r'<header><h3>Мотиваторы</h3>(.*?)</header>', panel).group(1)

    assert not header.strip(), "в заголовке блока осталась подпись: %r" % header


def test_descriptions_are_painted_for_every_drive(console_js):
    body = re.search(r'function paintDrive\(block, drive\)\{(.*?)\n  \}',
                     console_js, re.S).group(1)

    assert re.search(r'\.dsc', body), "описание не ищется в карточке"
    assert "drive.description" in body, "описание не подставляется"


def test_sent_message_is_not_shown_twice(console_js):
    """
    Своё сообщение показывается сразу из ответа на отправку, но у потока на
    сервере свой курсор — ту же реплику он присылает ещё раз. Без отсева по
    номеру каждое отправленное сообщение задваивалось.
    """
    body = re.search(r'function appendMessages\(rows\)\{(.*?)\n  \}',
                     console_js, re.S).group(1)

    assert re.search(r'row\.seq <= chatSeq', body), "показанное не отсеивается"
    assert "row.seq == null" in body, "история без номеров должна проходить"

    # Счётчик обязан двигаться только внутри appendMessages. Исключение одно:
    # после чтения истории он догоняет курсор сервера, иначе буфер потока
    # придёт вторым экземпляром той же переписки.
    moves = [line.strip() for line in console_js.splitlines()
             if re.match(r'\s*chatSeq = ', line)]
    assert moves == ["chatSeq = row.seq;", "chatSeq = res.status.seq || 0;"], \
        "счётчик реплик двигают из лишних мест: %s" % moves


def test_second_enter_does_not_send_again(console_js):
    """
    Кнопку блокирует `disabled`, но Enter вызывает `submit()` напрямую — второе
    нажатие отправляло тот же текст ещё раз.
    """
    body = re.search(r'function submit\(\)\{(.*?)\n  \}', console_js, re.S).group(1)

    assert re.search(r'if \(chatSending\) return', body), "нет защиты от повторной отправки"
    assert "chatSending = true" in body


def test_input_is_cleared_before_the_answer(console_js):
    """
    Поле очищалось по ответу сервера, и набранное за это время смешивалось с уже
    отправленным — в переписке появлялись обрывки вроде одиночной буквы.
    """
    body = re.search(r'function submit\(\)\{(.*?)\n  \}', console_js, re.S).group(1)

    before = body.index('input.value = ""')
    after = body.index("api.sendMessage")
    assert before < after, "поле очищается уже после отправки"

    assert body.count("input.value = text") == 2, \
        "текст не возвращается в поле при неудаче — набранное пропадёт"


def test_header_shows_the_boot_instead_of_pretending_to_work(console_js):
    """
    pid-файл появляется на первой секунде, а подъём идёт минутами — дольше
    всего качается модель эмбеддингов. Шапка молчала об этом, а окно консоли
    успевало написать «АГЕНТ РАБОТАЕТ».
    """
    body = re.search(r'if \(t\.phase === "starting"\) \{(.*?)\n    \}',
                     console_js, re.S).group(1)

    assert "Запускается" in body
    assert "t.bootStep" in body, "не видно, чем занят подъём"
    assert "showActivity" in body

    # опрос статуса процесса не должен перебивать журнал: он знает меньше
    guard = re.search(r'starting && \(!lastTick \|\| lastTick\.phase !== "starting"\)',
                      console_js)
    assert guard, "состояние процесса перебивает подробности из журнала"


def test_header_distinguishes_shutdown_from_startup(console_js):
    """Завершение выглядело запуском: pid-файла уже нет, а процесс ещё жив."""
    assert "Останавливается" in console_js
    assert re.search(r'stopping = !!res\.stopping', console_js), \
        "состояние остановки не читается"
