import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cache import Cache


def test_relative_path_resolved_against_module_dir():
    cache = Cache(Path("some/relative.json"), enabled=False)
    assert cache.path.is_absolute()
    assert cache.path == Path(__file__).parent.parent / "some/relative.json"


def test_absolute_path_kept_as_is(tmp_path):
    abs_path = tmp_path / "cache.json"
    cache = Cache(abs_path, enabled=False)
    assert cache.path == abs_path


def test_disabled_cache_never_reads_file_even_if_present(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"shows": {"x": 1}, "seerr_requests": None}))
    cache = Cache(path, enabled=False)
    assert cache.data == {"shows": {}, "seerr_requests": None}


def test_enabled_cache_missing_file_uses_default(tmp_path):
    cache = Cache(tmp_path / "missing.json", enabled=True)
    assert cache.data == {"shows": {}, "seerr_requests": None}


def test_enabled_cache_loads_existing_valid_file(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"shows": {"1": {"seasons": []}}}))
    cache = Cache(path, enabled=True)
    assert cache.data["shows"] == {"1": {"seasons": []}}
    assert cache.data["seerr_requests"] is None


def test_enabled_cache_corrupt_json_falls_back_to_default(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not valid json")
    cache = Cache(path, enabled=True)
    assert cache.data == {"shows": {}, "seerr_requests": None}


def test_enabled_cache_os_error_falls_back_to_default(tmp_path):
    # pointing "path" at a directory makes .open() raise IsADirectoryError (an OSError)
    dir_path = tmp_path / "a_directory"
    dir_path.mkdir()
    cache = Cache(dir_path, enabled=True)
    assert cache.data == {"shows": {}, "seerr_requests": None}


def test_clear_resets_data_but_not_counters(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"shows": {"1": {}}, "seerr_requests": None}))
    cache = Cache(path, enabled=True)
    cache.hits = 3
    cache.clear()
    assert cache.data == {"shows": {}, "seerr_requests": None}
    assert cache.hits == 3


def test_save_disabled_does_not_write_file(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path, enabled=False)
    cache.save()
    assert not path.exists()


def test_save_enabled_writes_file(tmp_path):
    path = tmp_path / "sub" / "cache.json"
    cache = Cache(path, enabled=True)
    cache.set_external_ids("1", "100", "200")
    cache.save()
    assert path.exists()
    on_disk = json.loads(path.read_text())
    assert on_disk["external_ids"]["1"] == {"tmdb_id": "100", "tvdb_id": "200"}


def test_save_os_error_is_caught_and_logged(tmp_path, caplog):
    # path.parent is a file, not a directory - mkdir(parents=True) raises OSError (NotADirectoryError)
    blocking_file = tmp_path / "blocking_file"
    blocking_file.write_text("x")
    cache = Cache(blocking_file / "cache.json", enabled=True)
    with caplog.at_level("WARNING"):
        cache.save()
    assert "Could not write cache file" in caplog.text


#################################################
# show seasons
#################################################
def _row(added_at="1", last_played="2", play_count=1):
    return {"added_at": added_at, "last_played": last_played, "play_count": play_count}


def test_get_show_seasons_disabled_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=False)
    assert cache.get_show_seasons("1", _row()) is None


def test_get_show_seasons_miss_when_absent(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    assert cache.get_show_seasons("1", _row()) is None
    assert cache.misses == 1


def test_get_show_seasons_miss_when_fingerprint_differs(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.set_show_seasons("1", _row(added_at="1"), seasons=[{"a": 1}])
    assert cache.get_show_seasons("1", _row(added_at="2")) is None
    assert cache.misses == 1


def test_get_show_seasons_hit_when_fingerprint_matches(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    row = _row()
    cache.set_show_seasons("1", row, seasons=[{"a": 1}])
    result = cache.get_show_seasons("1", row)
    assert result == [{"a": 1}]
    assert cache.hits == 1


def test_set_show_seasons_disabled_is_noop(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=False)
    cache.set_show_seasons("1", _row(), seasons=[{"a": 1}])
    assert cache.data["shows"] == {}


#################################################
# external ids
#################################################
def test_get_external_ids_disabled_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=False)
    assert cache.get_external_ids("1") is None


def test_get_external_ids_miss_when_absent(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    assert cache.get_external_ids("1") is None
    assert cache.ext_misses == 1


def test_get_external_ids_hit(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.set_external_ids("1", "tmdb1", "tvdb1")
    assert cache.get_external_ids("1") == ("tmdb1", "tvdb1")
    assert cache.ext_hits == 1


def test_set_external_ids_disabled_is_noop(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=False)
    cache.set_external_ids("1", "tmdb1", "tvdb1")
    assert "external_ids" not in cache.data


#################################################
# seerr requests ttl
#################################################
def test_get_seerr_requests_disabled_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=False)
    assert cache.get_seerr_requests(1) is None


def test_get_seerr_requests_missing_entry_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    assert cache.get_seerr_requests(1) is None


def test_get_seerr_requests_invalid_cached_at_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.data["seerr_requests"] = {"cached_at": "not-a-date", "requests": [1]}
    assert cache.get_seerr_requests(1) is None


def test_get_seerr_requests_missing_cached_at_key_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.data["seerr_requests"] = {"requests": [1]}
    assert cache.get_seerr_requests(1) is None


def test_get_seerr_requests_expired_returns_none(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    stale = datetime.now(timezone.utc) - timedelta(hours=5)
    cache.data["seerr_requests"] = {"cached_at": stale.isoformat(), "requests": [1, 2]}
    assert cache.get_seerr_requests(1) is None


def test_get_seerr_requests_within_ttl_returns_requests(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    fresh = datetime.now(timezone.utc) - timedelta(minutes=1)
    cache.data["seerr_requests"] = {"cached_at": fresh.isoformat(), "requests": [1, 2]}
    assert cache.get_seerr_requests(1) == [1, 2]


def test_set_seerr_requests_disabled_is_noop(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=False)
    cache.set_seerr_requests([1, 2])
    assert cache.data["seerr_requests"] is None


def test_set_seerr_requests_stores_cached_at_and_requests(tmp_path):
    cache = Cache(tmp_path / "c.json", enabled=True)
    cache.set_seerr_requests([1, 2])
    assert cache.data["seerr_requests"]["requests"] == [1, 2]
    assert "cached_at" in cache.data["seerr_requests"]
