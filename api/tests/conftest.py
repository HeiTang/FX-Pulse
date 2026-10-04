"""Keep persistent scheduler state isolated from all test runs."""

import pytest


@pytest.fixture(autouse=True)
def isolated_cooldown_state(tmp_path, monkeypatch):
    monkeypatch.setattr("fx_pulse.config.settings.scraper_state_file", tmp_path / "cooldowns.json")
