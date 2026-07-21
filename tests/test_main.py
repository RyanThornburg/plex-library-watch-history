from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import main
from cache import Cache
from clients import SeerrClient, TautulliClient
from models import MEDIA_TYPE_MOVIE, MEDIA_TYPE_SEASON, MEDIA_TYPE_SHOW, RequesterMaps


#################################################
# _configure_logging
#################################################
def test_configure_logging_creates_log_dir_and_file_handler(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(main, "LOG_DIR", log_dir)
    monkeypatch.setattr(main, "LOG_FILE", log_dir / "main.log")

    root_logger = __import__("logging").getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        main._configure_logging()
        assert log_dir.is_dir()
        assert (log_dir / "main.log").exists()
    finally:
        root_logger.handlers = original_handlers


#################################################
# _to_datetime
#################################################
@pytest.mark.parametrize("value", [None, "", "0", "-5", "not-a-number"])
def test_to_datetime_returns_none(value):
    assert main._to_datetime(value) is None


def test_to_datetime_parses_positive_epoch():
    result = main._to_datetime("1700000000")
    assert result == datetime.fromtimestamp(1700000000, tz=timezone.utc)


#################################################
# make_sort_key
#################################################
def test_make_sort_key_title(make_media_item):
    key_fn = main.make_sort_key("title")
    item = make_media_item(title="Zebra", season_number=3)
    assert key_fn(item) == ("zebra", 3)


def test_make_sort_key_requester(make_media_item):
    key_fn = main.make_sort_key("requester")
    item = make_media_item(title="Zebra", requester="Bob", season_number=1)
    assert key_fn(item) == ("bob", "zebra", 1)


def test_make_sort_key_last_watched_prefers_last_played(make_media_item):
    key_fn = main.make_sort_key("last_watched")
    watched = datetime(2020, 1, 1, tzinfo=timezone.utc)
    added = datetime(2019, 1, 1, tzinfo=timezone.utc)
    item = make_media_item(last_played=watched, added_at=added)
    assert key_fn(item)[0] == watched


def test_make_sort_key_last_watched_falls_back_to_added(make_media_item):
    key_fn = main.make_sort_key("last_watched")
    added = datetime(2019, 1, 1, tzinfo=timezone.utc)
    item = make_media_item(last_played=None, added_at=added)
    assert key_fn(item)[0] == added


def test_make_sort_key_last_watched_falls_back_to_epoch_min(make_media_item):
    key_fn = main.make_sort_key("last_watched")
    item = make_media_item(last_played=None, added_at=None)
    assert key_fn(item)[0] == datetime.min.replace(tzinfo=timezone.utc)


def test_make_sort_key_added(make_media_item):
    key_fn = main.make_sort_key("added")
    added = datetime(2019, 1, 1, tzinfo=timezone.utc)
    item = make_media_item(added_at=added, last_played=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert key_fn(item)[0] == added


def test_make_sort_key_added_falls_back_to_epoch_min(make_media_item):
    key_fn = main.make_sort_key("added")
    item = make_media_item(added_at=None)
    assert key_fn(item)[0] == datetime.min.replace(tzinfo=timezone.utc)


#################################################
# categorize_watches
#################################################
def test_categorize_watches_never_watched_bucket(make_media_item):
    old_enough = make_media_item(
        title="Old Movie", play_count=0, added_at=datetime.now(timezone.utc) - timedelta(days=200)
    )
    too_recent = make_media_item(
        title="New Movie", play_count=0, added_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    never, stale = main.categorize_watches(
        [old_enough, too_recent], days=180, sort_by="title", sort_order="asc", include_unknown=True
    )
    assert never == [old_enough]
    assert stale == []


def test_categorize_watches_stale_bucket(make_media_item):
    stale_item = make_media_item(
        title="Watched Long Ago",
        play_count=3,
        last_played=datetime.now(timezone.utc) - timedelta(days=200),
    )
    recently_watched = make_media_item(
        title="Watched Recently",
        play_count=1,
        last_played=datetime.now(timezone.utc) - timedelta(days=1),
    )
    never, stale = main.categorize_watches(
        [stale_item, recently_watched], days=180, sort_by="title", sort_order="asc", include_unknown=True
    )
    assert stale == [stale_item]
    assert never == []


def test_categorize_watches_excludes_unknown_requester_when_disabled(make_media_item):
    item = make_media_item(
        play_count=0,
        added_at=datetime.now(timezone.utc) - timedelta(days=200),
        requester=main.UNKNOWN_REQUESTER,
    )
    never, stale = main.categorize_watches(
        [item], days=180, sort_by="title", sort_order="asc", include_unknown=False
    )
    assert never == []


def test_categorize_watches_logs_warning_for_missing_added_at(make_media_item, caplog):
    item = make_media_item(play_count=0, added_at=None)
    with caplog.at_level("WARNING"):
        never, stale = main.categorize_watches(
            [item], days=180, sort_by="title", sort_order="asc", include_unknown=True
        )
    assert never == []
    assert "no added_at date" in caplog.text


def test_categorize_watches_logs_warning_for_missing_last_played(make_media_item, caplog):
    item = make_media_item(play_count=2, last_played=None)
    with caplog.at_level("WARNING"):
        never, stale = main.categorize_watches(
            [item], days=180, sort_by="title", sort_order="asc", include_unknown=True
        )
    assert stale == []
    assert "no last_played date" in caplog.text


def test_categorize_watches_sort_order_desc(make_media_item):
    a = make_media_item(
        title="Aaa", play_count=0, added_at=datetime.now(timezone.utc) - timedelta(days=200)
    )
    z = make_media_item(
        title="Zzz", play_count=0, added_at=datetime.now(timezone.utc) - timedelta(days=200)
    )
    never, _ = main.categorize_watches(
        [a, z], days=180, sort_by="title", sort_order="desc", include_unknown=True
    )
    assert [i.title for i in never] == ["Zzz", "Aaa"]


#################################################
# get_single_requester
#################################################
def test_get_single_requester_movie():
    requesters = RequesterMaps(movies={"100": "Alice"})
    item = MagicMock(media_type=MEDIA_TYPE_MOVIE, moviedb_id="100", season_number=None)
    assert main.get_single_requester(item, requesters) == "Alice"


def test_get_single_requester_tv_show_no_season():
    requesters = RequesterMaps(tv_shows={"200": "Bob"})
    item = MagicMock(media_type=MEDIA_TYPE_SHOW, tvdb_id="200", season_number=None)
    assert main.get_single_requester(item, requesters) == "Bob"


def test_get_single_requester_tv_season_specific_match():
    requesters = RequesterMaps(
        tv_shows={"200": "WholeShowRequester"}, tv_seasons={("200", 2): "SeasonRequester"}
    )
    item = MagicMock(media_type=MEDIA_TYPE_SEASON, tvdb_id="200", season_number=2)
    assert main.get_single_requester(item, requesters) == "SeasonRequester"


def test_get_single_requester_tv_season_falls_back_to_show():
    requesters = RequesterMaps(tv_shows={"200": "WholeShowRequester"})
    item = MagicMock(media_type=MEDIA_TYPE_SEASON, tvdb_id="200", season_number=5)
    assert main.get_single_requester(item, requesters) == "WholeShowRequester"


def test_get_single_requester_unknown_when_no_match():
    requesters = RequesterMaps()
    item = MagicMock(media_type=MEDIA_TYPE_MOVIE, moviedb_id="999", season_number=None)
    assert main.get_single_requester(item, requesters) == main.UNKNOWN_REQUESTER


#################################################
# get_requesters
#################################################
def test_get_requesters_uses_cache_when_available(monkeypatch, tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.set_seerr_requests([{"id": 1}])

    seerr_client_calls = []

    class _FakeSeerrClient(SeerrClient):
        def __init__(self, *a, **k):
            seerr_client_calls.append((a, k))

    monkeypatch.setattr(main, "SeerrClient", _FakeSeerrClient)

    maps = main.get_requesters(cache, "http://seerr", "key", ttl=1)
    assert seerr_client_calls == []
    assert maps == RequesterMaps()


def test_get_requesters_fetches_live_on_cache_miss(monkeypatch, tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)

    class _FakeSeerrClient(SeerrClient):
        def __init__(self, url, api_key, verify_ssl=True):
            self.url = url

        def fetch_all_requests(self):
            return [{"media": {"mediaType": "movie", "tmdbId": 1}, "requestedBy": {"displayName": "A"}}]

    monkeypatch.setattr(main, "SeerrClient", _FakeSeerrClient)

    maps = main.get_requesters(cache, "http://seerr", "key", ttl=1)
    assert maps.movies == {"1": "A"}
    assert cache.data["seerr_requests"]["requests"] == [
        {"media": {"mediaType": "movie", "tmdbId": 1}, "requestedBy": {"displayName": "A"}}
    ]


def test_get_requesters_no_ttl_always_fetches_live(monkeypatch, tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.set_seerr_requests([{"id": 1}])

    class _FakeSeerrClient(SeerrClient):
        def __init__(self, *a, **k):
            pass

        def fetch_all_requests(self):
            return []

    monkeypatch.setattr(main, "SeerrClient", _FakeSeerrClient)
    maps = main.get_requesters(cache, "http://seerr", "key", ttl=None)
    assert maps == RequesterMaps()


#################################################
# _guid_id / extract_external_ids
#################################################
def test_guid_id_dict():
    assert main._guid_id({"id": "tmdb://123"}) == "tmdb://123"


def test_guid_id_string():
    assert main._guid_id("tmdb://123") == "tmdb://123"


def test_extract_external_ids_new_agent():
    metadata = {"guids": [{"id": "tmdb://100"}, {"id": "tvdb://200"}]}
    assert main.extract_external_ids(metadata) == ("100", "200")


def test_extract_external_ids_new_agent_partial():
    metadata = {"guids": [{"id": "tmdb://100"}]}
    assert main.extract_external_ids(metadata) == ("100", "")


def test_extract_external_ids_legacy_fallback():
    metadata = {"guid": "com.plexapp.agents.themoviedb://555?lang=en"}
    assert main.extract_external_ids(metadata) == ("555", "")


def test_extract_external_ids_legacy_tvdb():
    metadata = {"guid": "com.plexapp.agents.thetvdb://777?lang=en"}
    assert main.extract_external_ids(metadata) == ("", "777")


def test_extract_external_ids_no_match_returns_empty():
    metadata = {}
    assert main.extract_external_ids(metadata) == ("", "")


#################################################
# fetch_external_ids
#################################################
def test_fetch_external_ids_returns_cached_without_calling_client(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.set_external_ids("1", "tmdb1", "tvdb1")
    client = MagicMock()
    result = main.fetch_external_ids(client, "1", cache)
    assert result == ("tmdb1", "tvdb1")
    client.get_metadata.assert_not_called()


def test_fetch_external_ids_fetches_and_caches_on_miss(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    client = MagicMock()
    client.get_metadata.return_value = {"guids": [{"id": "tmdb://5"}]}
    result = main.fetch_external_ids(client, "1", cache)
    assert result == ("5", "")
    assert cache.get_external_ids("1") == ("5", "")


def test_fetch_external_ids_no_cache_always_calls_client():
    client = MagicMock()
    client.get_metadata.return_value = {"guids": [{"id": "tmdb://5"}]}
    result = main.fetch_external_ids(client, "1", None)
    assert result == ("5", "")
    client.get_metadata.assert_called_once_with("1")


#################################################
# _season_watch_stats
#################################################
def test_season_watch_stats_returns_last_played_and_play_count():
    client = MagicMock()
    client.get_history.return_value = {"recordsFiltered": 7, "data": [{"date": 1700000000}]}
    last_played, play_count = main._season_watch_stats(client, "55")
    assert play_count == 7
    assert last_played == main._to_datetime("1700000000")
    client.get_history.assert_called_once_with(parent_rating_key="55", length=1)


def test_season_watch_stats_no_history_returns_none_and_zero():
    client = MagicMock()
    client.get_history.return_value = {"recordsFiltered": 0, "data": []}
    last_played, play_count = main._season_watch_stats(client, "55")
    assert last_played is None
    assert play_count == 0


#################################################
# _row_looks_falsely_unwatched
#################################################
def test_row_looks_falsely_unwatched_true_when_no_play_data_and_old():
    old_epoch = str(int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp()))
    row = {"last_played": None, "play_count": None, "added_at": old_epoch}
    assert main._row_looks_falsely_unwatched(row, days=180) is True


def test_row_looks_falsely_unwatched_false_when_has_play_count():
    row = {"last_played": None, "play_count": 3, "added_at": "1700000000"}
    assert main._row_looks_falsely_unwatched(row, days=180) is False


def test_row_looks_falsely_unwatched_false_when_has_last_played():
    row = {"last_played": "1700000000", "play_count": 0, "added_at": "1700000000"}
    assert main._row_looks_falsely_unwatched(row, days=180) is False


def test_row_looks_falsely_unwatched_false_when_added_at_missing():
    row = {"last_played": None, "play_count": 0, "added_at": None}
    assert main._row_looks_falsely_unwatched(row, days=180) is False


def test_row_looks_falsely_unwatched_false_when_too_recent():
    recent_epoch = str(int((datetime.now(timezone.utc) - timedelta(days=5)).timestamp()))
    row = {"last_played": None, "play_count": 0, "added_at": recent_epoch}
    assert main._row_looks_falsely_unwatched(row, days=180) is False


#################################################
# fetch_media_items
#################################################
class _FakeTautulliClient(TautulliClient):
    def __init__(
        self,
        libraries,
        items_by_section,
        items_by_rating_key=None,
        metadata=None,
        refreshed_items_by_section=None,
        history_by_rating_key=None,
    ):
        super().__init__(url="http://fake-tautulli", api_key="key")
        self._libraries = libraries
        self._items_by_section = items_by_section
        self._items_by_rating_key = items_by_rating_key or {}
        self._metadata = metadata or {}
        self._refreshed_items_by_section = refreshed_items_by_section or {}
        self._history_by_rating_key = history_by_rating_key or {}
        self.iter_items_calls = []

    def get_libraries(self):
        return self._libraries

    def iter_items(self, section_id=None, rating_key=None, page_size=500, refresh=False):
        self.iter_items_calls.append(
            {"section_id": section_id, "rating_key": rating_key, "refresh": refresh}
        )
        if rating_key is not None:
            yield from self._items_by_rating_key.get(rating_key, [])
        elif refresh:
            yield from self._refreshed_items_by_section.get(
                section_id, self._items_by_section.get(section_id, [])
            )
        else:
            yield from self._items_by_section.get(section_id, [])

    def get_metadata(self, rating_key):
        return self._metadata.get(rating_key, {})

    def get_history(self, parent_rating_key, length=1):
        return self._history_by_rating_key.get(
            parent_rating_key, {"recordsFiltered": 0, "data": []}
        )


def test_fetch_media_items_filters_to_movie_and_show_libraries():
    libraries = [
        {"section_id": "1", "section_name": "Movies", "section_type": "movie"},
        {"section_id": "2", "section_name": "Music", "section_type": "artist"},
    ]
    client = _FakeTautulliClient(libraries, items_by_section={"1": []})
    items = main.fetch_media_items(client, [], RequesterMaps(), days=180)
    assert items == []


def test_fetch_media_items_filters_by_library_names():
    libraries = [
        {"section_id": "1", "section_name": "Movies", "section_type": "movie"},
        {"section_id": "2", "section_name": "TV", "section_type": "show"},
    ]
    client = _FakeTautulliClient(
        libraries,
        items_by_section={
            "1": [{"rating_key": "10", "title": "M1", "added_at": "1700000000", "play_count": 0}],
            "2": [],
        },
    )
    items = main.fetch_media_items(client, ["movies"], RequesterMaps(), days=180)
    assert len(items) == 1
    assert items[0].title == "M1"


def test_fetch_media_items_builds_movie_item_with_requester():
    libraries = [{"section_id": "1", "section_name": "Movies", "section_type": "movie"}]
    client = _FakeTautulliClient(
        libraries,
        items_by_section={
            "1": [
                {
                    "rating_key": "10",
                    "title": "M1",
                    "added_at": "1700000000",
                    "last_played": None,
                    "play_count": 0,
                }
            ]
        },
        metadata={"10": {"guids": [{"id": "tmdb://55"}]}},
    )
    requesters = RequesterMaps(movies={"55": "Alice"})
    items = main.fetch_media_items(client, [], requesters, days=180)
    assert len(items) == 1
    item = items[0]
    assert item.moviedb_id == "55"
    assert item.requester == "Alice"
    assert item.media_type == MEDIA_TYPE_MOVIE


def test_fetch_media_items_skips_refresh_when_row_has_play_data():
    libraries = [{"section_id": "1", "section_name": "Movies", "section_type": "movie"}]
    row = {
        "rating_key": "10",
        "title": "M1",
        "added_at": "1700000000",
        "last_played": "1700000001",
        "play_count": 3,
    }
    client = _FakeTautulliClient(libraries, items_by_section={"1": [row]})
    items = main.fetch_media_items(client, [], RequesterMaps(), days=180)
    assert len(items) == 1
    assert [call["refresh"] for call in client.iter_items_calls] == [False]


def test_fetch_media_items_skips_refresh_when_item_too_new_to_report():
    recent_epoch = str(int((datetime.now(timezone.utc) - timedelta(days=5)).timestamp()))
    libraries = [{"section_id": "1", "section_name": "Movies", "section_type": "movie"}]
    row = {
        "rating_key": "10",
        "title": "M1",
        "added_at": recent_epoch,
        "last_played": None,
        "play_count": 0,
    }
    client = _FakeTautulliClient(libraries, items_by_section={"1": [row]})
    main.fetch_media_items(client, [], RequesterMaps(), days=180)
    assert [call["refresh"] for call in client.iter_items_calls] == [False]


def test_fetch_media_items_forces_refresh_when_row_looks_falsely_unwatched():
    libraries = [{"section_id": "1", "section_name": "Movies", "section_type": "movie"}]
    stale_row = {
        "rating_key": "10",
        "title": "M1",
        "added_at": "1700000000",
        "last_played": None,
        "play_count": None,
    }
    refreshed_row = {**stale_row, "last_played": "1750000000", "play_count": 5}
    client = _FakeTautulliClient(
        libraries,
        items_by_section={"1": [stale_row]},
        refreshed_items_by_section={"1": [refreshed_row]},
    )
    items = main.fetch_media_items(client, [], RequesterMaps(), days=180)
    assert len(items) == 1
    assert items[0].play_count == 5
    assert items[0].last_played == main._to_datetime("1750000000")
    assert [call["refresh"] for call in client.iter_items_calls] == [False, True]


def test_fetch_media_items_season_level_expands_seasons_and_uses_cache(tmp_path):
    libraries = [{"section_id": "1", "section_name": "TV", "section_type": "show"}]
    show_row = {
        "rating_key": "20",
        "title": "Show A",
        "media_type": "show",
        "added_at": "1700000000",
        "last_played": "1700000001",
        "play_count": 3,
    }
    season_rows = [
        {
            "rating_key": "21",
            "media_type": MEDIA_TYPE_SEASON,
            "media_index": "1",
            "added_at": "1700000000",
            "last_played": None,
            "play_count": None,
        },
        {"rating_key": "22", "media_type": "episode"},  # should be filtered out
    ]
    client = _FakeTautulliClient(
        libraries,
        items_by_section={"1": [show_row]},
        items_by_rating_key={"20": season_rows},
        metadata={"20": {}},
    )
    cache = Cache(tmp_path / "c.json", enabled=True)
    requesters = RequesterMaps()

    items = main.fetch_media_items(client, [], requesters, days=180, season_level=True, cache=cache)
    assert len(items) == 1
    assert items[0].media_type == MEDIA_TYPE_SEASON
    assert items[0].season_number == 1
    assert items[0].title == "Show A"

    # second call should hit the season cache instead of iterating rating_key again
    client._items_by_rating_key = {}
    items_again = main.fetch_media_items(
        client, [], requesters, days=180, season_level=True, cache=cache
    )
    assert len(items_again) == 1


def test_fetch_media_items_season_level_pulls_stats_from_get_history(tmp_path):
    """get_library_media_info never carries season-level play stats, so
    season rows have to be patched from get_history before being cached."""
    libraries = [{"section_id": "1", "section_name": "TV", "section_type": "show"}]
    show_row = {
        "rating_key": "20",
        "title": "Show A",
        "media_type": "show",
        "added_at": "1700000000",
        "last_played": "1750000000",
        "play_count": 10,
    }
    season_row = {
        "rating_key": "21",
        "media_type": MEDIA_TYPE_SEASON,
        "media_index": "1",
        "added_at": "1700000000",
        "last_played": None,
        "play_count": None,
    }
    client = _FakeTautulliClient(
        libraries,
        items_by_section={"1": [show_row]},
        items_by_rating_key={"20": [season_row]},
        metadata={"20": {}},
        history_by_rating_key={"21": {"recordsFiltered": 4, "data": [{"date": 1751000000}]}},
    )
    cache = Cache(tmp_path / "c.json", enabled=True)

    items = main.fetch_media_items(
        client, [], RequesterMaps(), days=180, season_level=True, cache=cache
    )
    assert len(items) == 1
    assert items[0].play_count == 4
    assert items[0].last_played == main._to_datetime("1751000000")

    # the corrected stats should be what gets cached, not the original nulls
    cached_seasons = cache.get_show_seasons("20", show_row)
    assert cached_seasons is not None
    assert cached_seasons[0]["play_count"] == 4
    assert cached_seasons[0]["last_played"] == 1751000000


def test_fetch_media_items_without_season_level_keeps_show_as_single_item():
    libraries = [{"section_id": "1", "section_name": "TV", "section_type": "show"}]
    show_row = {
        "rating_key": "20",
        "title": "Show A",
        "media_type": "show",
        "added_at": "1700000000",
        "last_played": "1700000001",
        "play_count": 2,
    }
    client = _FakeTautulliClient(libraries, items_by_section={"1": [show_row]})
    items = main.fetch_media_items(client, [], RequesterMaps(), days=180, season_level=False)
    assert len(items) == 1
    assert items[0].media_type == "show"
    assert items[0].season_number is None


#################################################
# main()
#################################################
def _patch_common_main_deps(monkeypatch, *, seerr_configured: bool):
    monkeypatch.setattr(main, "_configure_logging", lambda: None)

    connection = MagicMock()
    connection.tautulli.require_configured.return_value = ("http://tautulli", "key")
    connection.tautulli.verify_ssl = True
    connection.cache.cache_file = None
    connection.cache.cache_enabled = True
    connection.cache.seer_cache_ttl_hours = 1
    if seerr_configured:
        connection.seerr.api_key.get_secret_value.return_value = "seerr-key"
        connection.seerr.url = "http://seerr"
        connection.seerr.verify_ssl = True
    else:
        connection.seerr.api_key = None
        connection.seerr.url = None

    report = MagicMock()
    report.days_unwatched = 180
    report.season_level = False
    report.library_names = []
    report.disable_cache = False
    report.refresh_cache = False
    report.sort_by = "title"
    report.sort_order = "asc"
    report.include_unknown_requester = True
    report.include_never_watched = True
    report.include_stale_watched = True
    report.group_by = None
    report.export_csv = None

    monkeypatch.setattr(main, "ConnectionSettings", lambda: connection)
    monkeypatch.setattr(main, "ReportSettings", lambda: report)
    monkeypatch.setattr(main, "TautulliClient", MagicMock())

    fake_cache = MagicMock()
    fake_cache.ext_hits = 0
    fake_cache.ext_misses = 0
    fake_cache.hits = 0
    fake_cache.misses = 0
    monkeypatch.setattr(main, "Cache", lambda *a, **k: fake_cache)
    monkeypatch.setattr(main, "fetch_media_items", lambda *a, **k: [])
    print_report_mock = MagicMock()
    export_csv_mock = MagicMock()
    monkeypatch.setattr(main, "print_report", print_report_mock)
    monkeypatch.setattr(main, "export_csv", export_csv_mock)

    return connection, report, fake_cache, print_report_mock, export_csv_mock


def test_main_without_seerr_configured(monkeypatch):
    connection, report, fake_cache, print_report_mock, export_csv_mock = _patch_common_main_deps(
        monkeypatch, seerr_configured=False
    )
    get_requesters_mock = MagicMock()
    monkeypatch.setattr(main, "get_requesters", get_requesters_mock)

    main.main()

    get_requesters_mock.assert_not_called()
    print_report_mock.assert_called_once()
    fake_cache.save.assert_called_once()


def test_main_with_seerr_configured_and_csv_export(monkeypatch, tmp_path):
    connection, report, fake_cache, print_report_mock, export_csv_mock = _patch_common_main_deps(
        monkeypatch, seerr_configured=True
    )
    report.export_csv = tmp_path / "out.csv"
    get_requesters_mock = MagicMock(return_value=RequesterMaps())
    monkeypatch.setattr(main, "get_requesters", get_requesters_mock)

    main.main()

    get_requesters_mock.assert_called_once()
    export_csv_mock.assert_called_once()


def test_main_season_level_logs_season_cache_stats(monkeypatch):
    connection, report, fake_cache, print_report_mock, export_csv_mock = _patch_common_main_deps(
        monkeypatch, seerr_configured=False
    )
    report.season_level = True
    monkeypatch.setattr(main, "get_requesters", MagicMock())

    main.main()

    fake_cache.save.assert_called_once()


def test_main_refresh_cache_clears_cache(monkeypatch):
    connection, report, fake_cache, print_report_mock, export_csv_mock = _patch_common_main_deps(
        monkeypatch, seerr_configured=False
    )
    report.refresh_cache = True
    monkeypatch.setattr(main, "get_requesters", MagicMock())

    main.main()

    fake_cache.clear.assert_called_once()


def test_main_excludes_never_and_stale_when_disabled(monkeypatch):
    connection, report, fake_cache, print_report_mock, export_csv_mock = _patch_common_main_deps(
        monkeypatch, seerr_configured=False
    )
    report.include_never_watched = False
    report.include_stale_watched = False
    monkeypatch.setattr(main, "get_requesters", MagicMock())
    monkeypatch.setattr(
        main,
        "categorize_watches",
        lambda *a, **k: (["never_item"], ["stale_item"]),
    )

    main.main()

    print_report_mock.assert_called_once_with([], [], 180, None)
