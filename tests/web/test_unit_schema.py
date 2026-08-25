# -*- coding: utf-8 -*-
"""
Согласованность карты полей с настоящими конфигами.

`schema.py` — единственное место, где описано соответствие «контрол ↔ ключ».
Если во фреймворке переименуют или уберут параметр, эти тесты упадут раньше,
чем консоль молча перестанет его записывать.
"""

import pytest

from src.web import config_io as cio
from src.web import schema

MISSING = object()


def _settings():
    """Рабочий конфиг, а в свежем клоне (и в CI) — образец: рабочего там нет."""
    from tests.web.conftest import source_config

    return cio.load_yaml(source_config(cio.SETTINGS_FILE, cio.SETTINGS_EXAMPLE))


@pytest.mark.parametrize("path", sorted(set(schema.SETTINGS_FIELDS.values())))
def test_mapped_path_exists_in_settings(path):
    """Каждый путь из карты существует в config/settings.yaml."""
    assert cio.get_path(_settings(), path, MISSING) is not MISSING, path


@pytest.mark.parametrize("path", sorted(schema.SETTINGS_LISTS.values()))
def test_mapped_list_exists_and_is_a_list(path):
    node = cio.get_path(_settings(), path, MISSING)
    assert node is not MISSING, path
    assert isinstance(node, list), "%s не список: %r" % (path, type(node))


def test_mapped_paths_point_at_leaves():
    """Путь должен вести к значению, а не к вложенному словарю."""
    data = _settings()
    for cfg_key, path in schema.SETTINGS_FIELDS.items():
        node = cio.get_path(data, path)
        assert not isinstance(node, dict), "%s ведёт к словарю" % cfg_key


def test_cfg_keys_have_source_prefix():
    """Ключ вида `источник:путь` — по префиксу сервер решает, куда писать."""
    for key in schema.SETTINGS_FIELDS:
        assert key.startswith("settings:"), key
        assert key[len("settings:"):] == schema.SETTINGS_FIELDS[key], key
    for key in schema.ENV_FIELDS:
        assert key.startswith("env:"), key


def test_no_duplicate_targets():
    """Два контрола не должны писать в один ключ — иначе они будут спорить."""
    paths = list(schema.SETTINGS_FIELDS.values())
    dupes = {p for p in paths if paths.count(p) > 1}
    assert not dupes, "дубликаты: %s" % sorted(dupes)


def test_example_config_covers_the_same_paths():
    """
    settings.example.yaml — образец для новых установок. Если путь есть в карте,
    но отсутствует в образце, у нового пользователя поле будет пустым.
    """
    example = cio.load_yaml(cio.ROOT_DIR / "config" / "settings.example.yaml")
    missing = [p for p in schema.SETTINGS_FIELDS.values()
               if cio.get_path(example, p, MISSING) is MISSING]
    assert not missing, "нет в образце: %s" % missing


# ---------------------------------------------------------------- интерфейсы

def _interfaces():
    from tests.web.conftest import source_config

    return cio.load_yaml(source_config(cio.INTERFACES_FILE, cio.INTERFACES_EXAMPLE))


@pytest.mark.parametrize("path", sorted(set(schema.INTERFACES_FIELDS.values())))
def test_interface_path_exists(path):
    """Каждый путь карты существует в config/interfaces.yaml."""
    assert cio.get_path(_interfaces(), path, MISSING) is not MISSING, path


def test_interfaces_map_covers_every_leaf():
    """
    Обратная проверка: в конфиге нет параметра, для которого не нашлось поля.
    Иначе он останется невидимым и неизменяемым через консоль.
    """
    listed = set(schema.INTERFACES_FIELDS.values())
    known_lists = set(schema.INTERFACES_LISTS.values())
    known_lists |= {p for p, _ in schema.INTERFACES_OBJECT_LISTS.values()}

    leaves, lists = [], []

    def walk(node, path=()):
        for key, value in node.items():
            here = path + (key,)
            if isinstance(value, dict):
                walk(value, here)
            elif isinstance(value, list):
                lists.append(".".join(here))
            else:
                leaves.append(".".join(here))

    walk(_interfaces())
    assert not (set(leaves) - listed), "нет полей для: %s" % sorted(set(leaves) - listed)
    assert not (set(lists) - known_lists), "нет редакторов для: %s" % sorted(set(lists) - known_lists)


@pytest.mark.parametrize("path", sorted(schema.INTERFACES_LISTS.values()))
def test_interface_list_exists(path):
    node = cio.get_path(_interfaces(), path, MISSING)
    assert node is not MISSING and isinstance(node, list), path


def test_object_lists_declare_real_keys():
    """У списка словарей ключи должны совпадать с тем, что лежит в файле."""
    data = _interfaces()
    for path, keys in schema.INTERFACES_OBJECT_LISTS.values():
        rows = cio.get_path(data, path)
        assert isinstance(rows, list), path
        for row in rows:
            assert set(row) == set(keys), "%s: %s против %s" % (path, sorted(row), keys)


def test_interface_cfg_keys_have_source_prefix():
    for key, path in schema.INTERFACES_FIELDS.items():
        assert key == "interfaces:" + path, key


def test_example_interfaces_cover_the_same_paths():
    example = cio.load_yaml(cio.ROOT_DIR / "config" / "interfaces.example.yaml")
    missing = [p for p in schema.INTERFACES_FIELDS.values()
               if cio.get_path(example, p, MISSING) is MISSING]
    assert not missing, "нет в образце: %s" % missing
