# -*- coding: utf-8 -*-
"""
Механика чтения и записи конфигов.

Консоль правит файлы, в которых комментарии несут документацию, а отступы —
смысл. Эти тесты сторожат ровно одно: правка одного значения меняет одну строку
и больше ничего.
"""

import io

import pytest
import yaml

from src.web import config_io as cio


# ---------------------------------------------------------------- YAML: скаляры

def test_scalar_changes_only_one_line(sandbox_config):
    """Правка значения не должна задевать соседние строки."""
    before = sandbox_config.settings_lines()
    lines = list(before)
    assert cio.set_scalar(lines, "system.heartbeat_interval", 420)

    diff = [i for i, (a, b) in enumerate(zip(before, lines)) if a != b]
    assert len(diff) == 1, "изменилось строк: %d" % len(diff)
    assert "420" in lines[diff[0]]


def test_scalar_keeps_trailing_comment_and_alignment(sandbox_config):
    """Комментарий и пробелы перед ним — часть строки, их нельзя схлопывать."""
    lines = sandbox_config.settings_lines()
    original = next(l for l in lines if "mode:" in l and "tree_of_thoughts" not in l)
    tail = original[original.index("#"):]
    gap = original[:original.index("#")]
    gap = gap[len(gap.rstrip()):]

    cio.set_scalar(lines, "system.tree_of_thoughts.mode", "hybrid")
    changed = next(l for l in lines if "mode:" in l and "#" in l)

    assert changed.endswith(gap + tail), "потеряно выравнивание или комментарий"
    assert '"hybrid"' in changed, "кавычки исходного значения не сохранены"


@pytest.mark.parametrize("path, new, expected", [
    ("llm.temperature", 0.35, "temperature: 0.35"),          # float остаётся float
    ("llm.temperature", 2, "temperature: 2.0"),              # 1.0 не превращается в 1
    ("llm.max_react_steps", 22, "max_react_steps: 22"),      # int остаётся int
    ("llm.max_react_steps", "18", "max_react_steps: 18"),    # строка из формы -> int
    ("llm.is_multimodal", True, "is_multimodal: true"),      # bool в YAML-стиле
    ("llm.is_multimodal", "false", "is_multimodal: false"),
])
def test_scalar_preserves_type(sandbox_config, path, new, expected):
    """Тип значения берётся из файла, а не из того, что прислал браузер."""
    lines = sandbox_config.settings_lines()
    assert cio.set_scalar(lines, path, new)
    assert any(l.strip() == expected for l in lines), expected


def test_scalar_refuses_unknown_path(sandbox_config):
    """Новых ключей консоль не создаёт — иначе разъедется со схемой фреймворка."""
    lines = sandbox_config.settings_lines()
    assert cio.set_scalar(lines, "llm.no_such_key", 1) is False
    assert cio.set_scalar(lines, "llm", 1) is False, "узел-словарь не лист"


# ---------------------------------------------------------------- YAML: списки

def test_list_replaced_with_indent_and_comments_intact(sandbox_config):
    """У списка моделей ниже идёт комментарий — он обязан уцелеть."""
    lines = sandbox_config.settings_lines()
    comment = next(l for l in lines if "можно добавить свои" in l)

    assert cio.set_list(lines, "llm.available_models", ["a-1", "b-2", "c-3"])

    start = lines.index("  available_models:")
    block = []
    for line in lines[start + 1:]:
        if not line.strip().startswith("- "):
            break
        block.append(line)

    assert comment in lines, "комментарий после списка потерян"
    assert block == ["    - a-1", "    - b-2", "    - c-3"], block


# ---------------------------------------------------------------- файл целиком

def test_apply_settings_keeps_newlines_and_stays_valid(sandbox_config):
    """CRLF и валидность YAML переживают запись."""
    raw_before = sandbox_config.settings_path.read_bytes()
    crlf_before = raw_before.count(b"\r\n")

    missing = cio.apply_settings({"system.timezone": 3}, {})
    assert missing == []

    raw_after = sandbox_config.settings_path.read_bytes()
    assert raw_after.count(b"\r\n") == crlf_before, "переводы строк изменились"

    data = yaml.safe_load(io.open(sandbox_config.settings_path, encoding="utf-8"))
    assert data["system"]["timezone"] == 3


def test_untouched_blocks_are_byte_identical(sandbox_config):
    """
    Блок system.subconscious в settings.yaml свёрстан с нестандартным отступом.
    Полный round-trip через ruamel его нормализовал — построчная запись не должна.
    """
    before = sandbox_config.settings_lines()
    cio.apply_settings({"llm.temperature": 0.5}, {})
    after = sandbox_config.settings_lines()

    diff = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(diff) == 1, "затронуто строк: %d -> %r" % (len(diff), diff[:5])
    assert "temperature" in diff[0][1]


# ---------------------------------------------------------------- .env

def test_env_value_replaced_in_place(sandbox_config):
    """Значение меняется на месте, порядок и комментарии не едут."""
    before = sandbox_config.env_text().replace("\r\n", "\n").split("\n")
    cio.save_env({"LLM_API_URL": "https://example.dev/v1/"}, {})
    after = sandbox_config.env_text().replace("\r\n", "\n").split("\n")

    assert len(before) == len(after), "число строк изменилось"
    diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(diff) == 1
    assert after[diff[0]] == 'LLM_API_URL="https://example.dev/v1/"'


def test_env_prefixed_keys_are_renumbered(sandbox_config):
    """Ключи LLM_API_KEY_N перенумеровываются сквозняком, заготовки убираются."""
    cio.save_env({}, {"LLM_API_KEY_": ["one", "two", "three"]})
    text = sandbox_config.env_text()

    assert 'LLM_API_KEY_1="one"' in text
    assert 'LLM_API_KEY_2="two"' in text
    assert 'LLM_API_KEY_3="three"' in text
    assert "# LLM_API_KEY_2" not in text, "закомментированная заготовка осталась"
    assert cio.env_prefixed("LLM_API_KEY_") == ["one", "two", "three"]


def test_env_shrinking_list_removes_extra_lines(sandbox_config):
    """Удаление ключа в интерфейсе должно убирать строку, а не оставлять дырку."""
    cio.save_env({}, {"LLM_API_KEY_": ["a", "b", "c"]})
    cio.save_env({}, {"LLM_API_KEY_": ["a"]})
    text = sandbox_config.env_text()

    assert 'LLM_API_KEY_1="a"' in text
    assert "LLM_API_KEY_2" not in text
    assert "LLM_API_KEY_3" not in text


def test_env_new_variable_appended(sandbox_config):
    """Переменной может не быть в файле — тогда она дописывается в конец."""
    assert "SUB_LLM_API_URL" not in cio.load_env()
    cio.save_env({"SUB_LLM_API_URL": "https://sub.example/"}, {})
    assert cio.load_env()["SUB_LLM_API_URL"] == "https://sub.example/"


def test_env_ignores_commented_variables(sandbox_config):
    """Закомментированная переменная не считается заданной."""
    env = sandbox_config.env_path
    with io.open(env, "a", encoding="utf-8") as fh:
        fh.write('\n# GHOST_KEY="value"\n')
    assert "GHOST_KEY" not in cio.load_env()
