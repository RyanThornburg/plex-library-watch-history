import json

import pytest
import responses
from responses import matchers

from clients import SeerrClient, TautulliClient


#################################################
# TautulliClient
#################################################
def test_tautulli_strips_trailing_slash_and_sets_endpoint():
    client = TautulliClient(url="http://tautulli.example/", api_key="key")
    assert client.url == "http://tautulli.example"
    assert client.endpoint == "http://tautulli.example/api/v2"


@responses.activate
def test_tautulli_call_returns_data_on_success():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    responses.add(
        responses.GET,
        "http://tautulli.example/api/v2",
        json={"response": {"result": "success", "data": {"foo": "bar"}}},
        match=[matchers.query_param_matcher({"apikey": "key", "cmd": "get_libraries"})],
    )
    result = client._call("get_libraries")
    assert result == {"foo": "bar"}


@responses.activate
def test_tautulli_call_raises_runtime_error_on_api_failure():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    responses.add(
        responses.GET,
        "http://tautulli.example/api/v2",
        json={"response": {"result": "error", "message": "bad api key"}},
    )
    with pytest.raises(RuntimeError, match="bad api key"):
        client._call("get_libraries")


@responses.activate
def test_tautulli_call_raises_on_http_error():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    responses.add(
        responses.GET,
        "http://tautulli.example/api/v2",
        status=500,
    )
    with pytest.raises(Exception):
        client._call("get_libraries")


@responses.activate
def test_tautulli_get_libraries():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    responses.add(
        responses.GET,
        "http://tautulli.example/api/v2",
        json={"response": {"result": "success", "data": [{"section_id": "1"}]}},
    )
    assert client.get_libraries() == [{"section_id": "1"}]


@responses.activate
def test_tautulli_get_library_media_info_passes_section_and_rating_key():
    client = TautulliClient(url="http://tautulli.example", api_key="key")

    def request_callback(request):
        assert "section_id=5" in request.url
        assert "rating_key=99" in request.url
        return (200, {}, '{"response": {"result": "success", "data": {}}}')

    responses.add_callback(
        responses.GET,
        "http://tautulli.example/api/v2",
        callback=request_callback,
    )
    client.get_library_media_info(section_id="5", rating_key="99")


@responses.activate
def test_tautulli_iter_items_paginates_until_short_page():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    page1 = {"response": {"result": "success", "data": {"data": [{"id": 1}, {"id": 2}]}}}
    page2 = {"response": {"result": "success", "data": {"data": [{"id": 3}]}}}
    responses.add(responses.GET, "http://tautulli.example/api/v2", json=page1)
    responses.add(responses.GET, "http://tautulli.example/api/v2", json=page2)

    items = list(client.iter_items(section_id="1", page_size=2))
    assert items == [{"id": 1}, {"id": 2}, {"id": 3}]


@responses.activate
def test_tautulli_iter_items_stops_on_empty_page():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    responses.add(
        responses.GET,
        "http://tautulli.example/api/v2",
        json={"response": {"result": "success", "data": {"data": []}}},
    )
    assert list(client.iter_items(section_id="1")) == []


@responses.activate
def test_tautulli_get_library_media_info_passes_refresh_true():
    client = TautulliClient(url="http://tautulli.example", api_key="key")

    def request_callback(request):
        assert "refresh=true" in request.url
        return (200, {}, '{"response": {"result": "success", "data": {}}}')

    responses.add_callback(
        responses.GET, "http://tautulli.example/api/v2", callback=request_callback
    )
    client.get_library_media_info(section_id="5", refresh=True)


@responses.activate
def test_tautulli_get_library_media_info_omits_refresh_by_default():
    client = TautulliClient(url="http://tautulli.example", api_key="key")

    def request_callback(request):
        assert "refresh" not in request.url
        return (200, {}, '{"response": {"result": "success", "data": {}}}')

    responses.add_callback(
        responses.GET, "http://tautulli.example/api/v2", callback=request_callback
    )
    client.get_library_media_info(section_id="5")


@responses.activate
def test_tautulli_iter_items_only_passes_refresh_on_first_page():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    page1 = {"response": {"result": "success", "data": {"data": [{"id": 1}, {"id": 2}]}}}
    page2 = {"response": {"result": "success", "data": {"data": [{"id": 3}]}}}
    pages = [page1, page2]
    seen_refresh = []

    def request_callback(request):
        seen_refresh.append("refresh=true" in request.url)
        return (200, {}, json.dumps(pages.pop(0)))

    responses.add_callback(
        responses.GET, "http://tautulli.example/api/v2", callback=request_callback
    )
    responses.add_callback(
        responses.GET, "http://tautulli.example/api/v2", callback=request_callback
    )

    items = list(client.iter_items(section_id="1", page_size=2, refresh=True))
    assert items == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert seen_refresh == [True, False]


@responses.activate
def test_tautulli_get_metadata():
    client = TautulliClient(url="http://tautulli.example", api_key="key")
    responses.add(
        responses.GET,
        "http://tautulli.example/api/v2",
        json={"response": {"result": "success", "data": {"guid": "abc"}}},
    )
    assert client.get_metadata("42") == {"guid": "abc"}


@responses.activate
def test_tautulli_get_history_passes_parent_rating_key_and_sort():
    client = TautulliClient(url="http://tautulli.example", api_key="key")

    def request_callback(request):
        assert "parent_rating_key=50" in request.url
        assert "order_column=date" in request.url
        assert "order_dir=desc" in request.url
        assert "length=1" in request.url
        body = json.dumps(
            {
                "response": {
                    "result": "success",
                    "data": {"recordsFiltered": 3, "data": [{"date": 123}]},
                }
            }
        )
        return (200, {}, body)

    responses.add_callback(
        responses.GET, "http://tautulli.example/api/v2", callback=request_callback
    )
    result = client.get_history(parent_rating_key="50")
    assert result == {"recordsFiltered": 3, "data": [{"date": 123}]}


#################################################
# SeerrClient
#################################################
def test_seerr_strips_trailing_slash_sets_endpoint_and_header():
    client = SeerrClient(url="http://seerr.example/", api_key="key")
    assert client.url == "http://seerr.example"
    assert client.endpoint == "http://seerr.example/api/v1"
    assert client.session.headers["X-Api-Key"] == "key"


@responses.activate
def test_seerr_iter_requests_paginates_until_short_page():
    client = SeerrClient(url="http://seerr.example", api_key="key")
    page1 = {"results": [{"id": 1}, {"id": 2}]}
    page2 = {"results": [{"id": 3}]}
    responses.add(responses.GET, "http://seerr.example/api/v1/request", json=page1)
    responses.add(responses.GET, "http://seerr.example/api/v1/request", json=page2)

    items = list(client.iter_requests(page_size=2))
    assert items == [{"id": 1}, {"id": 2}, {"id": 3}]


@responses.activate
def test_seerr_iter_requests_stops_on_empty_results():
    client = SeerrClient(url="http://seerr.example", api_key="key")
    responses.add(responses.GET, "http://seerr.example/api/v1/request", json={"results": []})
    assert list(client.iter_requests()) == []


@responses.activate
def test_seerr_fetch_all_requests():
    client = SeerrClient(url="http://seerr.example", api_key="key")
    responses.add(
        responses.GET,
        "http://seerr.example/api/v1/request",
        json={"results": [{"id": 1}]},
    )
    assert client.fetch_all_requests() == [{"id": 1}]


def test_build_maps_from_requests_movie():
    reqs = [
        {
            "media": {"mediaType": "movie", "tmdbId": 100},
            "requestedBy": {"displayName": "Alice"},
        }
    ]
    maps = SeerrClient.build_maps_from_requests(reqs)
    assert maps.movies == {"100": "Alice"}
    assert maps.tv_shows == {}
    assert maps.tv_seasons == {}


def test_build_maps_from_requests_tv_show_and_seasons():
    reqs = [
        {
            "media": {"mediaType": "tv", "tvdbId": 200},
            "requestedBy": {"displayName": "Bob"},
            "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}],
        }
    ]
    maps = SeerrClient.build_maps_from_requests(reqs)
    assert maps.tv_shows == {"200": "Bob"}
    assert maps.tv_seasons == {("200", 1): "Bob", ("200", 2): "Bob"}


def test_build_maps_from_requests_multiple_requesters_collapse_sorted():
    reqs = [
        {"media": {"mediaType": "movie", "tmdbId": 1}, "requestedBy": {"displayName": "Zed"}},
        {"media": {"mediaType": "movie", "tmdbId": 1}, "requestedBy": {"displayName": "Amy"}},
    ]
    maps = SeerrClient.build_maps_from_requests(reqs)
    assert maps.movies == {"1": "Amy, Zed"}


@pytest.mark.parametrize(
    "requested_by, expected",
    [
        ({"displayName": "Alice"}, "Alice"),
        ({"username": "alice99"}, "alice99"),
        ({"plexUsername": "alice_plex"}, "alice_plex"),
        ({"id": 7}, "user#7"),
        ({}, "Unknown"),
    ],
)
def test_build_maps_from_requests_username_fallback_chain(requested_by, expected):
    reqs = [{"media": {"mediaType": "movie", "tmdbId": 1}, "requestedBy": requested_by}]
    maps = SeerrClient.build_maps_from_requests(reqs)
    assert maps.movies == {"1": expected}


def test_build_maps_from_requests_skips_missing_ids_and_unknown_type():
    reqs = [
        {"media": {"mediaType": "movie"}, "requestedBy": {"displayName": "A"}},
        {"media": {"mediaType": "tv"}, "requestedBy": {"displayName": "B"}},
        {"media": {"mediaType": "music"}, "requestedBy": {"displayName": "C"}},
        {"media": {}, "requestedBy": {}},
    ]
    maps = SeerrClient.build_maps_from_requests(reqs)
    assert maps.movies == {}
    assert maps.tv_shows == {}
    assert maps.tv_seasons == {}
