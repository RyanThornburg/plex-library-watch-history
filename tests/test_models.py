from datetime import datetime, timedelta, timezone

from models import UNKNOWN_REQUESTER, MediaItem, RequesterMaps


def test_requester_maps_defaults_are_independent_per_instance():
    a = RequesterMaps()
    b = RequesterMaps()
    a.movies["1"] = "alice"
    assert b.movies == {}
    assert a.movies is not b.movies


def test_media_item_display_title_without_season(make_media_item):
    item = make_media_item(title="Movie A", season_number=None)
    assert item.display_title == "Movie A"


def test_media_item_display_title_with_season(make_media_item):
    item = make_media_item(title="Show A", season_number=2)
    assert item.display_title == "Show A - Season 2"


def test_media_item_requester_defaults_unknown(make_media_item):
    item = make_media_item()
    assert item.requester == UNKNOWN_REQUESTER


def test_days_since_added_none_when_missing(make_media_item):
    item = make_media_item(added_at=None)
    assert item.days_since_added is None


def test_days_since_added_computed(make_media_item):
    added = datetime.now(timezone.utc) - timedelta(days=10)
    item = make_media_item(added_at=added)
    assert item.days_since_added == 10


def test_days_since_watched_none_when_missing(make_media_item):
    item = make_media_item(last_played=None)
    assert item.days_since_watched is None


def test_days_since_watched_computed(make_media_item):
    watched = datetime.now(timezone.utc) - timedelta(days=5)
    item = make_media_item(last_played=watched)
    assert item.days_since_watched == 5
