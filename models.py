"""
Classes for reading data from tautulli and seer and caching the data
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

UNKNOWN_REQUESTER = "Unknown"
UNKNOWN_TITLE = "Unknown Title"


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
    added_at: Optional[datetime]
    last_played: Optional[datetime]
    play_count: int
    moviedb_id: str = ""
    tvdb_id: str = ""
    season_number: Optional[int] = None
    requester: str = field(default=UNKNOWN_REQUESTER)

    @property
    def display_title(self) -> str:
        """add season number if it exists"""
        if self.season_number is not None:
            return f"{self.title} - Season {self.season_number}"
        return self.title

    @property
    def days_since_added(self) -> Optional[int]:
        """calculate days since it was added"""
        if not self.added_at:
            return None
        return (datetime.now(timezone.utc) - self.added_at).days

    @property
    def days_since_watched(self) -> Optional[int]:
        """calculate days since watched"""
        if not self.last_played:
            return None
        return (datetime.now(timezone.utc) - self.last_played).days
