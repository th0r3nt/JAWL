# -*- coding: utf-8 -*-
"""
Общие фикстуры для тестов веб-консоли.

Главное правило: ни один тест не притрагивается к настоящим `config/settings.yaml`
и `.env`. Все проверки записи идут по копиям во временном каталоге.
"""

import io
import shutil

import pytest

from src.web import config_io as cio

ROOT = cio.ROOT_DIR
WEB_DIR = ROOT / "web"


def source_config(real, example):
    """
    Откуда брать конфиг для теста.

    Рабочие `settings.yaml`, `interfaces.yaml` и `.env` перечислены в
    `.gitignore`, поэтому в свежем клоне (и в CI) их нет — есть только образцы.
    Берём рабочий файл, если он есть, иначе образец. Создавать рабочие файлы
    здесь нельзя: тесты не должны оставлять следов в репозитории.
    """
    if real.exists():
        return real
    if example.exists():
        return example
    pytest.skip("нет ни %s, ни образца" % real.name)


@pytest.fixture(scope="session")
def settings_yaml():
    """Рабочие настройки, а в свежем клоне — образец."""
    return cio.load_yaml(source_config(cio.SETTINGS_FILE, cio.SETTINGS_EXAMPLE))


@pytest.fixture(scope="session")
def interfaces_yaml():
    return cio.load_yaml(source_config(cio.INTERFACES_FILE, cio.INTERFACES_EXAMPLE))


@pytest.fixture
def sandbox_config(tmp_path, monkeypatch):
    """
    Копия настоящих конфигов во временном каталоге.

    Возвращает объект с путями и хелперами чтения, а модуль config_io
    перенаправлен на копии — записи в репозиторий не произойдёт.
    """
    settings = tmp_path / "settings.yaml"
    interfaces = tmp_path / "interfaces.yaml"
    env = tmp_path / ".env"
    shutil.copy(source_config(cio.SETTINGS_FILE, cio.SETTINGS_EXAMPLE), settings)
    shutil.copy(source_config(cio.INTERFACES_FILE, cio.INTERFACES_EXAMPLE), interfaces)
    shutil.copy(source_config(cio.ENV_FILE, cio.ENV_EXAMPLE), env)

    monkeypatch.setattr(cio, "SETTINGS_FILE", settings)
    monkeypatch.setattr(cio, "INTERFACES_FILE", interfaces)
    monkeypatch.setattr(cio, "ENV_FILE", env)

    class Sandbox:
        settings_path = settings
        interfaces_path = interfaces
        env_path = env

        @staticmethod
        def settings_text() -> str:
            return io.open(settings, encoding="utf-8", newline="").read()

        @staticmethod
        def env_text() -> str:
            return io.open(env, encoding="utf-8", newline="").read()

        @staticmethod
        def interfaces_text() -> str:
            return io.open(interfaces, encoding="utf-8", newline="").read()

        @staticmethod
        def settings_lines():
            return Sandbox.settings_text().replace("\r\n", "\n").split("\n")

    return Sandbox


@pytest.fixture(scope="session")
def index_html() -> str:
    return io.open(WEB_DIR / "index.html", encoding="utf-8").read()


@pytest.fixture(scope="session")
def console_js() -> str:
    return io.open(WEB_DIR / "console.js", encoding="utf-8").read()


@pytest.fixture(scope="session")
def styles_css() -> str:
    return io.open(WEB_DIR / "styles.css", encoding="utf-8").read()
