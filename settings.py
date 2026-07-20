"""Settings schema: CLI args -> config.toml -> field defaults, highest to lowest priority."""

from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from models import GroupBy, SortBy, SortOrder

CONFIG_PATH = Path(__file__).parent / "config.toml"


class HelperConfig(BaseModel):
    """Config for tautulli and seerr"""

    url: str | None = None
    api_key: SecretStr | None = None
    verify_ssl: bool = True

    def require_configured(self, name: str) -> tuple[str, str]:
        """Return (url, api_key), raising if either is unset."""
        if self.url is None or self.api_key is None:
            raise ValueError(
                f"Missing {name} configuration: url and api_key must be set"
            )
        return self.url, self.api_key.get_secret_value()


class CacheSettings(BaseModel):
    """Config for caching tautulli results"""

    cache_enabled: bool = True
    cache_file: Path = Path(".cache/tautulli_report_cache.json")
    seer_cache_ttl_hours: int = 1


class ConnectionSettings(BaseSettings):
    """Tautulli/Seerr credentials and cache

    `cache_enabled` lives here too, but `--disable-cache` on ReportSettings
    lets you override it for a single run without editing the file.
    """

    model_config = SettingsConfigDict(toml_file=CONFIG_PATH, extra="ignore")
    tautulli: HelperConfig = HelperConfig()
    seerr: HelperConfig = HelperConfig()
    cache: CacheSettings = CacheSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, TomlConfigSettingsSource(settings_cls))


class ReportSettings(BaseSettings):
    """Report options you'd want to change on the fly, without opening the config file."""

    model_config = SettingsConfigDict(
        toml_file=CONFIG_PATH,
        cli_parse_args=True,
        cli_kebab_case=True,
        cli_prog_name="main.py",
        cli_implicit_flags=True,
        extra="ignore",
    )

    days_unwatched: int = 180
    library_names: list[str] = []
    season_level: bool = False
    sort_by: SortBy = "title"
    sort_order: SortOrder = "asc"
    group_by: GroupBy | None = None
    include_never_watched: bool = True
    include_stale_watched: bool = True
    include_unknown_requester: bool = True

    # CLI-only
    export_csv: Path | None = None
    refresh_cache: bool = False
    disable_cache: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # First = highest priority. `cli_parse_args=True` in model_config
        # makes pydantic-settings auto-prepend a CLI source ahead of
        # whatever we return here, so this just adds the TOML file below
        # the constructor kwargs.
        return (init_settings, TomlConfigSettingsSource(settings_cls))
