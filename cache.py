"""cache.py"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


#################################################
# Local Cache
#################################################
@dataclass
class Cache:
    """
    Caching to json file to minimize time for
        - per show season data
        - seerr request lists
    Should only be used as an optimization, failures shouldn't
    raise issues, just fall back to live fetch
    """

    path: Path
    enabled: bool
    hits: int = 0
    misses: int = 0
    ext_hits: int = 0
    ext_misses: int = 0
    data: dict[str, Any] = field(init=False, default_factory=dict[str, Any])

    def __post_init__(self):
        if not self.path.is_absolute():
            self.path = Path(__file__).parent / self.path

        self.data = self._load()

    @staticmethod
    def _default_cache_dict() -> dict[str, Any]:
        return {"shows": {}, "seerr_requests": None}

    def _load(self) -> dict[str, Any]:
        if not self.enabled or not self.path.exists():
            return self._default_cache_dict()

        try:
            with self.path.open(encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("shows", {})
            data.setdefault("seerr_requests", None)
            return data
        except json.JSONDecodeError, OSError:
            return self._default_cache_dict()

    def clear(self):
        """clear cache file"""
        self.data = self._default_cache_dict()

    def save(self) -> None:
        """save cache file"""
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except OSError as e:
            logger.warning("Could not write cache file(%s)", e)

    @staticmethod
    def _show_fingerprint(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "added_at": row.get("added_at"),
            "last_played": row.get("last_played"),
            "play_count": row.get("play_count"),
        }

    def get_show_seasons(
        self, show_rating_key: str, current_row: dict[str, Any]
    ) -> list[Any] | None:
        """check cache if show exists/matches"""

        if not self.enabled:
            return None
        show_entry = self.data.get("shows", {}).get(show_rating_key)
        if not show_entry:
            self.misses += 1
            return None
        if show_entry.get("fingerprint") != self._show_fingerprint(current_row):
            self.misses += 1
            return None

        self.hits += 1
        return show_entry.get("seasons")

    def set_show_seasons(
        self, show_rating_key: str, current_row: dict[str, Any], seasons: list[Any]
    ) -> None:
        """add show fingerprint to cache"""

        if not self.enabled:
            return

        self.data.setdefault("shows", {})[show_rating_key] = {
            "fingerprint": self._show_fingerprint(current_row),
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "seasons": seasons,
        }

    def get_external_ids(self, rating_key: str) -> tuple[str, str] | None:
        """rating key should never change and be safe to cache once plex matches it"""
        if not self.enabled:
            return None

        entry = self.data.get("external_ids", {}).get(rating_key)
        if entry is None:
            self.ext_misses += 1
            return None

        self.ext_hits += 1
        return entry.get("tmdb_id", ""), entry.get("tvdb_id", "")

    def set_external_ids(self, rating_key: str, tmdb_id: str, tvdb_id: str):
        """save external ids to cache"""
        if not self.enabled:
            return
        self.data.setdefault("external_ids", {})[rating_key] = {
            "tmdb_id": tmdb_id,
            "tvdb_id": tvdb_id,
        }

    def get_seerr_requests(self, ttl_hours: int) -> list[Any] | None:
        """check cache for seerr requests"""

        if not self.enabled:
            return None

        entry = self.data.get("seerr_requests")
        if not entry:
            return None

        try:
            cached_at = datetime.fromisoformat(entry["cached_at"])
        except KeyError, ValueError:
            return None

        if datetime.now(timezone.utc) - cached_at > timedelta(hours=ttl_hours):
            return None

        return entry.get("requests")

    def set_seerr_requests(self, requests_list: list[Any]) -> None:
        """add seerr requets to cache"""

        if not self.enabled:
            return

        self.data["seerr_requests"] = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "requests": requests_list,
        }
