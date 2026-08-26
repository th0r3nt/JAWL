# -*- coding: utf-8 -*-
"""
Чтение и запись конфигурации для веб-консоли.

Ядро фреймворка не импортируется и не изменяется — модуль работает с файлами
напрямую.

Про запись. Полный round-trip через ruamel.yaml сохраняет комментарии, но
нормализует то, чего не касались: отступы списков, хвостовые пробелы, блоки с
нестандартным отступом (`system.subconscious` в settings.yaml как раз такой), и
теряет комментарий, привязанный к последнему элементу списка. Поэтому читаем
через ruamel (структура и типы), а пишем построчно — меняется ровно та строка,
которую правил человек, остальной файл остаётся байт в байт.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ruamel.yaml import YAML

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"
INTERFACES_FILE = ROOT_DIR / "config" / "interfaces.yaml"
ENV_FILE = ROOT_DIR / ".env"

# Рабочих конфигов нет в репозитории — они в .gitignore и создаются из образцов
# при первой настройке. Консоль можно открыть раньше, чем это произошло.
SETTINGS_EXAMPLE = ROOT_DIR / "config" / "settings.example.yaml"
INTERFACES_EXAMPLE = ROOT_DIR / "config" / "interfaces.example.yaml"
ENV_EXAMPLE = ROOT_DIR / ".env.example"

# Личность агента. Тоже пользовательские файлы: перечислены в `.gitignore`,
# в репозитории лежат только заготовки. Но, в отличие от конфигов, их не
# создаёт никто — ни онбординг, ни мастер настройки. А сборщик промпта явно
# отбрасывает `*.example.md` (`_gather_markdown` в l3_agent/prompt/builder.py),
# поэтому без них агент работает вообще без описания характера — и молча.
PERSONALITY_DIR = ROOT_DIR / "src" / "l3_agent" / "prompt" / "personality"
SOUL_FILE = PERSONALITY_DIR / "SOUL.md"
SOUL_EXAMPLE = PERSONALITY_DIR / "SOUL.example.md"
STYLE_FILE = PERSONALITY_DIR / "EXAMPLES_OF_STYLE.md"
STYLE_EXAMPLE = PERSONALITY_DIR / "EXAMPLES_OF_STYLE.example.md"

EXAMPLES = (
    (SETTINGS_FILE, SETTINGS_EXAMPLE),
    (INTERFACES_FILE, INTERFACES_EXAMPLE),
    (ENV_FILE, ENV_EXAMPLE),
    (SOUL_FILE, SOUL_EXAMPLE),
    (STYLE_FILE, STYLE_EXAMPLE),
)


def framework_version() -> str:
    """
    Версия фреймворка из `src/__init__.py`.

    Читаем текстом, а не импортом: `src` тянет за собой пакет целиком, а нам
    нужна одна строка — и нужна она даже тогда, когда что-то в пакете не
    импортируется.
    """
    init = ROOT_DIR / "src" / "__init__.py"
    try:
        text = init.read_text(encoding="utf-8")
    except OSError:
        return ""

    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    return match.group(1) if match else ""


def ensure_config_files() -> list:
    """
    Создаёт недостающие рабочие файлы из образцов.

    В свежем клоне есть только `*.example`: рабочие файлы перечислены в
    `.gitignore`. Для конфигов так же поступает мастер настройки в CLI
    (`_ensure_base_files_exist` в `src/cli/screens/onboarding.py`) — без них
    консоль падала бы при первом же чтении.

    Файлы личности он не создаёт, а нужны они не меньше: без `SOUL.md` агент
    поднимается и работает, но без всякого описания характера, потому что
    заготовки `*.example.md` сборщик промпта отбрасывает. Молчаливая потеря,
    поэтому чиним здесь же.

    Возвращает список созданных файлов, чтобы об этом можно было сказать вслух.
    """
    import shutil

    created = []
    for target, example in EXAMPLES:
        if target.exists() or not example.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(example, target)
        created.append(target.name)
    return created

_yaml = YAML()
_yaml.preserve_quotes = True


# ---------------------------------------------------------------- общее

def detect_newline(path: Path) -> str:
    """Файлы проекта в CRLF; записать их в LF — показать git весь файл изменённым."""
    if not path.exists():
        return "\n"
    raw = path.read_bytes()
    return "\r\n" if raw.count(b"\r\n") > raw.count(b"\n") // 2 else "\n"


def _read_lines(path: Path) -> List[str]:
    return io.open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n").split("\n")


def _write_lines(path: Path, lines: List[str]) -> None:
    nl = detect_newline(path)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(lines))


# ---------------------------------------------------------------- чтение YAML

def load_yaml(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    with io.open(path, encoding="utf-8") as fh:
        return _yaml.load(fh)


def get_path(data, dotted: str, default=None):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


# ---------------------------------------------------------------- поиск строки ключа

_KEY_RE = re.compile(r'^(\s*)([A-Za-z_][\w-]*)\s*:(.*)$')


def _find_key(lines: List[str], dotted: str) -> Tuple[Optional[int], Optional[re.Match]]:
    """Индекс строки, объявляющей ключ по точечному пути (или None)."""
    parts = dotted.split(".")
    stack: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _KEY_RE.match(line)
        if not m:
            continue
        indent, key = len(m.group(1)), m.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if [k for _, k in stack] + [key] == parts:
            return i, m
        stack.append((indent, key))
    return None, None


def _split_comment(rest: str) -> Tuple[str, str]:
    """
    Отделяет значение от хвостового комментария, не путаясь с '#' внутри кавычек.

    Второй элемент — хвост целиком, вместе с пробелами перед '#': в файле они
    служат выравниванием, и схлопывать их значит менять строку без нужды.
    """
    quote = None
    for i, ch in enumerate(rest):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or rest[i - 1] in " \t"):
            value = rest[:i].rstrip()
            return value, rest[len(value):]
    value = rest.rstrip()
    tail = rest[len(value):]
    return value, tail if tail.strip() else ""


def _format_value(old_raw: str, value: Any) -> str:
    """Форматирует новое значение в стиле старого: кавычки, тип, вид числа."""
    old = old_raw.strip()
    quote = old[0] if len(old) >= 2 and old[0] == old[-1] and old[0] in "\"'" else ""

    if isinstance(value, bool) or old in ("true", "false"):
        flag = value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
        return "true" if flag else "false"

    # число с точкой должно остаться числом с точкой: 1.0 не превращается в 1
    if re.fullmatch(r'-?\d+\.\d+', old):
        return repr(float(value))
    if re.fullmatch(r'-?\d+', old):
        return str(int(float(value)))

    text = "" if value is None else str(value)
    return "%s%s%s" % (quote, text, quote) if quote else text


def set_scalar(lines: List[str], dotted: str, value: Any) -> bool:
    """Переписывает значение листа, сохраняя отступ и хвостовой комментарий."""
    i, m = _find_key(lines, dotted)
    if i is None:
        return False
    old_value, tail = _split_comment(m.group(3))
    if not old_value.strip():
        return False                     # это узел-словарь, а не лист
    new_value = _format_value(old_value, value)
    lines[i] = "%s%s: %s%s" % (m.group(1), m.group(2), new_value, tail)
    return True


def set_list(lines: List[str], dotted: str, items: List[str]) -> bool:
    """
    Переписывает YAML-список, сохраняя отступ элементов и всё, что вокруг:
    комментарии до, между и после блока остаются на местах.
    """
    i, m = _find_key(lines, dotted)
    if i is None:
        return False
    key_indent = len(m.group(1))

    # список может быть записан в строку: `available_voices: []`
    inline, tail = _split_comment(m.group(3))
    if inline.strip().startswith("["):
        if not items:
            lines[i] = "%s%s: []%s" % (m.group(1), m.group(2), tail)
            return True
        lines[i] = "%s%s:%s" % (m.group(1), m.group(2), tail)
        block = ["%s  - %s" % (m.group(1), x) for x in items]
        lines[i + 1:i + 1] = block
        return True

    item_idx: List[int] = []
    item_prefix = " " * (key_indent + 2) + "- "
    quote = ""                            # элементы могли быть в кавычках
    j = i + 1
    while j < len(lines):
        line = lines[j]
        lm = re.match(r'^(\s*)-\s?(.*)$', line)
        if lm and len(lm.group(1)) > key_indent:
            if not item_idx:
                item_prefix = lm.group(1) + "- "
                raw = lm.group(2).strip()
                if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                    quote = raw[0]
            item_idx.append(j)
            j += 1
            continue
        if line.strip() == "" or line.lstrip().startswith("#"):
            j += 1                        # комментарий или пустая строка внутри блока
            continue
        break

    if not items:
        # пустой список записываем в строку, иначе получится ключ без значения
        if item_idx:
            del lines[item_idx[0]:item_idx[-1] + 1]
        lines[i] = "%s%s: []%s" % (m.group(1), m.group(2), tail)
        return True

    block = [item_prefix + "%s%s%s" % (quote, x, quote) for x in items]
    if item_idx:
        lines[item_idx[0]:item_idx[-1] + 1] = block
    else:
        lines[i + 1:i + 1] = block
    return True


def set_object_list(lines: List[str], dotted: str, items: List[dict], keys: List[str]) -> bool:
    """
    Переписывает список словарей — так устроен `web.rss.feeds`:

        feeds:
          - name: "Habr"
            url: "https://…"

    Первый ключ идёт следом за дефисом, остальные выравниваются под него.
    """
    i, m = _find_key(lines, dotted)
    if i is None:
        return False
    key_indent = len(m.group(1))
    inline, tail = _split_comment(m.group(3))

    start = i + 1
    end = i + 1
    item_indent = " " * (key_indent + 2)
    while end < len(lines):
        line = lines[end]
        if not line.strip():
            end += 1
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= key_indent:
            break
        if line.lstrip().startswith("- "):
            item_indent = " " * indent
        end += 1
    while end > start and not lines[end - 1].strip():
        end -= 1                          # пустые строки после блока не трогаем

    if not items:
        del lines[start:end]
        lines[i] = "%s%s: []%s" % (m.group(1), m.group(2), tail)
        return True

    lines[i] = "%s%s:%s" % (m.group(1), m.group(2), tail)
    block: List[str] = []
    for item in items:
        for n, key in enumerate(keys):
            value = str(item.get(key, ""))
            prefix = item_indent + ("- " if n == 0 else "  ")
            block.append('%s%s: "%s"' % (prefix, key, value))
    lines[start:end] = block
    return True


# ---------------------------------------------------------------- .env

_ENV_LINE = re.compile(r'^(\s*)(#\s*)?([A-Z][A-Z0-9_]*)\s*=\s*(.*)$')


def _unquote(raw: str) -> str:
    raw = _split_comment(raw)[0].strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def load_env() -> Dict[str, str]:
    """Активные (незакомментированные) переменные .env в порядке файла."""
    out: Dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for line in _read_lines(ENV_FILE):
        m = _ENV_LINE.match(line)
        if m and not m.group(2):
            out[m.group(3)] = _unquote(m.group(4))
    return out


def env_prefixed(prefix: str) -> List[str]:
    """
    Значения ключей PREFIX_1, PREFIX_2 … по возрастанию номера.

    Так же их собирает src/main.py — перебором окружения по префиксу,
    а не по фиксированным именам.
    """
    found: List[Tuple[int, str]] = []
    for key, value in load_env().items():
        m = re.match(r'^' + re.escape(prefix) + r'(\d+)$', key)
        if m:
            found.append((int(m.group(1)), value))
    found.sort()
    return [v for _, v in found]


def save_env(values: Dict[str, str], prefixed: Optional[Dict[str, List[str]]] = None) -> None:
    """
    Точечно правит .env: комментарии, порядок и пояснения остаются на местах.

    * `values` — обычные переменные: заменяются на месте, отсутствующие
      дописываются в конец;
    * `prefixed` — списки {"LLM_API_KEY_": [...]}: перенумеровываются сквозняком,
      лишние строки (в том числе закомментированные заготовки) убираются.
    """
    lines = _read_lines(ENV_FILE) if ENV_FILE.exists() else []
    prefixed = prefixed or {}

    remaining = dict(values)
    for i, line in enumerate(lines):
        m = _ENV_LINE.match(line)
        if not m or m.group(2):
            continue
        key = m.group(3)
        if key in remaining:
            _, tail = _split_comment(m.group(4))
            lines[i] = '%s%s="%s"%s' % (m.group(1), key, remaining.pop(key), tail)
    for key, value in remaining.items():
        lines.append('%s="%s"' % (key, value))

    for prefix, items in prefixed.items():
        pat = re.compile(r'^\s*(#\s*)?' + re.escape(prefix) + r'\d+\s*=')
        hits = [i for i, l in enumerate(lines) if pat.match(l)]
        block = ['%s%d="%s"' % (prefix, n + 1, v) for n, v in enumerate(items)]
        if not hits:
            lines.extend(block)
            continue
        first = hits[0]
        for i in reversed(hits):
            del lines[i]
        lines[first:first] = block

    _write_lines(ENV_FILE, lines)


# ---------------------------------------------------------------- фасад для settings.yaml

def apply_yaml(path: Path,
               scalars: Dict[str, Any],
               lists: Optional[Dict[str, List[str]]] = None,
               object_lists: Optional[Dict[str, tuple]] = None) -> List[str]:
    """
    Применяет правки к YAML-файлу. Возвращает пути, которых в файле не нашлось.

    `object_lists`: {путь: (элементы, порядок_ключей)} — для списков словарей.
    """
    lines = _read_lines(path)
    lists = lists or {}
    object_lists = object_lists or {}
    missing: List[str] = []

    for dotted, value in scalars.items():
        if not set_scalar(lines, dotted, value):
            missing.append(dotted)
    for dotted, items in lists.items():
        if not set_list(lines, dotted, items):
            missing.append(dotted)
    for dotted, (items, keys) in object_lists.items():
        if not set_object_list(lines, dotted, items, keys):
            missing.append(dotted)

    total = len(scalars) + len(lists) + len(object_lists)
    if total > len(missing):
        _write_lines(path, lines)
    return missing


def apply_settings(scalars: Dict[str, Any], lists: Dict[str, List[str]]) -> List[str]:
    """Совместимость: правки в config/settings.yaml."""
    return apply_yaml(SETTINGS_FILE, scalars, lists)
