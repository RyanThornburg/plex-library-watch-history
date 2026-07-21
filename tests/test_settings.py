"""
Tests use subclasses with model_config pointed at a temp TOML file rather than
the real repo config.toml (which holds live credentials and is intentionally
skip-worktree'd) - settings_customise_sources is inherited unchanged and reads
whatever toml_file is set on the settings_cls passed to it.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from settings import CacheSettings, ConnectionSettings, HelperConfig, ReportSettings


def test_helper_config_require_configured_raises_when_unset():
    helper = HelperConfig()
    with pytest.raises(ValueError, match="Missing Tautulli configuration"):
        helper.require_configured("Tautulli")


def test_helper_config_require_configured_raises_when_only_url_set():
    helper = HelperConfig(url="http://example.com")
    with pytest.raises(ValueError, match="Missing Tautulli configuration"):
        helper.require_configured("Tautulli")


def test_helper_config_require_configured_returns_url_and_secret():
    helper = HelperConfig(url="http://example.com", api_key="secret123")
    url, api_key = helper.require_configured("Tautulli")
    assert url == "http://example.com"
    assert api_key == "secret123"


def test_cache_settings_defaults():
    cache = CacheSettings()
    assert cache.cache_enabled is True
    assert cache.cache_file == Path(".cache/tautulli_report_cache.json")
    assert cache.seer_cache_ttl_hours == 1


def _write_toml(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_connection_settings_reads_from_toml(tmp_path):
    toml_path = _write_toml(
        tmp_path / "config.toml",
        """
[tautulli]
url = "http://tautulli.example"
api_key = "abc123"
verify_ssl = false

[cache]
cache_enabled = false
seer_cache_ttl_hours = 4
""",
    )

    class _TestConnectionSettings(ConnectionSettings):
        model_config = SettingsConfigDict(toml_file=toml_path, extra="ignore")

    settings = _TestConnectionSettings()
    assert settings.tautulli.url == "http://tautulli.example"
    assert settings.tautulli.api_key.get_secret_value() == "abc123"
    assert settings.tautulli.verify_ssl is False
    assert settings.cache.cache_enabled is False
    assert settings.cache.seer_cache_ttl_hours == 4
    # seerr wasn't in the TOML - field default applies
    assert settings.seerr.url is None


def test_connection_settings_init_kwargs_override_toml(tmp_path):
    toml_path = _write_toml(
        tmp_path / "config.toml",
        """
[tautulli]
url = "http://tautulli.example"
api_key = "abc123"
""",
    )

    class _TestConnectionSettings(ConnectionSettings):
        model_config = SettingsConfigDict(toml_file=toml_path, extra="ignore")

    settings = _TestConnectionSettings(tautulli=HelperConfig(url="http://override", api_key="xyz"))
    assert settings.tautulli.url == "http://override"


def _report_settings_cls(toml_path: Path):
    class _TestReportSettings(ReportSettings):
        model_config = SettingsConfigDict(
            toml_file=toml_path,
            cli_parse_args=True,
            cli_kebab_case=True,
            cli_prog_name="main.py",
            cli_implicit_flags=True,
            extra="ignore",
        )

    return _TestReportSettings


def test_report_settings_falls_back_to_toml_when_no_cli_args(tmp_path):
    toml_path = _write_toml(tmp_path / "config.toml", "days_unwatched = 99\n")
    cls = _report_settings_cls(toml_path)

    settings = cls(_cli_parse_args=[])
    assert settings.days_unwatched == 99


def test_report_settings_cli_overrides_toml(tmp_path):
    toml_path = _write_toml(tmp_path / "config.toml", "days_unwatched = 99\n")
    cls = _report_settings_cls(toml_path)

    settings = cls(_cli_parse_args=["--days-unwatched", "10"])
    assert settings.days_unwatched == 10


def test_report_settings_falls_back_to_field_default(tmp_path):
    toml_path = _write_toml(tmp_path / "config.toml", "")
    cls = _report_settings_cls(toml_path)

    settings = cls(_cli_parse_args=[])
    assert settings.days_unwatched == 180


def test_report_settings_cli_list_and_flags(tmp_path):
    toml_path = _write_toml(tmp_path / "config.toml", "")
    cls = _report_settings_cls(toml_path)

    settings = cls(
        _cli_parse_args=[
            "--library-names",
            "Movies",
            "--library-names",
            "TV Shows",
            "--sort-by",
            "requester",
            "--disable-cache",
        ]
    )
    assert settings.library_names == ["Movies", "TV Shows"]
    assert settings.sort_by == "requester"
    assert settings.disable_cache is True


def test_report_settings_rejects_invalid_sort_by(tmp_path):
    toml_path = _write_toml(tmp_path / "config.toml", "")
    cls = _report_settings_cls(toml_path)

    with pytest.raises(ValidationError):
        cls(_cli_parse_args=["--sort-by", "not-a-real-option"])
