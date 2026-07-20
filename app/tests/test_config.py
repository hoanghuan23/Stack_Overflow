from __future__ import annotations

from app.core import config


def test_get_settings_loads_stackexchange_key_from_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("STACKEXCHANGE_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STACKEXCHANGE_KEY", raising=False)

    config.load_dotenv(dotenv_path=env_file, override=True)

    settings = config.get_settings()

    assert settings.stackexchange_key == "dotenv-key"


def test_get_settings_prefers_existing_environment_over_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("STACKEXCHANGE_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.setenv("STACKEXCHANGE_KEY", "env-key")

    config.load_dotenv(dotenv_path=env_file, override=False)

    settings = config.get_settings()

    assert settings.stackexchange_key == "env-key"
