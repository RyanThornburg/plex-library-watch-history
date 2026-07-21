"""Shared fixtures for the test suite."""

from datetime import datetime, timedelta, timezone

import pytest

from models import MediaItem

NOW = datetime.now(timezone.utc)


@pytest.fixture
def make_media_item():
    """Factory for MediaItem with sane defaults, override via kwargs."""

    def _make(**overrides) -> MediaItem:
        defaults: dict = {
            "title": "Some Title",
            "media_type": "movie",
            "library_name": "Movies",
            "rating_key": "123",
            "added_at": NOW - timedelta(days=10),
            "last_played": None,
            "play_count": 0,
        }
        defaults.update(overrides)
        return MediaItem(**defaults)

    return _make
