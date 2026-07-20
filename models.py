"""
Classes for reading data from tautulli and seer and caching the data
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

UNKNOWN_REQUESTER = "Unknown"
UNKNOWN_TITLE = "Unknown Title"

# Tautulli's vocabulary for section/media type (Seerr uses "tv" instead of "show" - see clients.py)
MEDIA_TYPE_MOVIE = "movie"
MEDIA_TYPE_SHOW = "show"
MEDIA_TYPE_SEASON = "season"

SortBy = Literal["title", "last_watched", "requester"]
SortOrder = Literal["asc", "desc"]
GroupBy = Literal["none", "requester", "media_type"]
Status = Literal["never_watched", "stale_watched"]

STATUS_NEVER_WATCHED: Status = "never_watched"
STATUS_STALE_WATCHED: Status = "stale_watched"


#################################################
# RequesterMaps
#################################################
@dataclass
class RequesterMaps:
    """id -> requester name lookups built from Seerr's request list."""

    movies: dict[str, str] = field(default_factory=dict[str, str])
    tv_seasons: dict[tuple[str, int], str] = field(
        default_factory=dict[tuple[str, int], str]
    )
    tv_shows: dict[str, str] = field(default_factory=dict[str, str])


#################################################
# MediaItem
#################################################
@dataclass
class MediaItem:
    """data related to the media item"""

    title: str
    media_type: str
    library_name: str
    rating_key: str
    added_at: datetime | None
    last_played: datetime | None
    play_count: int
    moviedb_id: str = ""
    tvdb_id: str = ""
    season_number: int | None = None
    requester: str = field(default=UNKNOWN_REQUESTER)

    @property
    def display_title(self) -> str:
        """add season number if it exists"""
        if self.season_number is not None:
            return f"{self.title} - Season {self.season_number}"
        return self.title

    @property
    def days_since_added(self) -> int | None:
        """calculate days since it was added"""
        if not self.added_at:
            return None
        return (datetime.now(timezone.utc) - self.added_at).days

    @property
    def days_since_watched(self) -> int | None:
        """calculate days since watched"""
        if not self.last_played:
            return None
        return (datetime.now(timezone.utc) - self.last_played).days
