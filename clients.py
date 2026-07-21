"""
Classes for reading data from tautulli and seer and caching the data
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Generator

import requests

from models import MEDIA_TYPE_MOVIE, UNKNOWN_REQUESTER, RequesterMaps

API_TIMEOUT_SEC = 45
# Seerr's vocabulary for media type ("tv" where Tautulli uses "show" - see models.py)
_SEERR_MEDIA_TYPE_TV = "tv"
logger = logging.getLogger(__name__)


#################################################
# Seerr Client
#################################################
@dataclass
class SeerrClient:
    """client for reading data from seerr"""

    url: str
    api_key: str = field(repr=False)
    session: requests.Session = field(
        init=False, default_factory=requests.Session, repr=False
    )
    verify_ssl: bool = True
    endpoint: str = ""

    def __post_init__(self):
        self.url = self.url.rstrip("/")
        self.endpoint = f"{self.url}/api/v1"
        self.session.headers["X-Api-Key"] = self.api_key

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.session.get(
            f"{self.endpoint}{path}",
            params=params,
            verify=self.verify_ssl,
            timeout=API_TIMEOUT_SEC,
        )
        response.raise_for_status()
        return response.json()

    def iter_requests(self, page_size: int = 100) -> Generator[Any, None, None]:
        """yield request records handling pagination"""
        skip = 0
        while True:
            page = self._get(
                "/request", take=page_size, skip=skip, filter="all", sort="added"
            )
            results = page.get("results", [])
            if not results:
                return
            yield from results

            skip += len(results)
            if len(results) < page_size:
                return

    def fetch_all_requests(self) -> list[Any]:
        """fetch all requests"""
        return list(self.iter_requests())

    @staticmethod
    def build_maps_from_requests(requests_list: list[Any]) -> RequesterMaps:
        """
        convert seerr to lookup maps
            - movies: str(tmdbid) -> names
            - tv_seasons: (str(tvdbid), season_number) -> names
            - tv_shows: str(tvdbid) -> names (fallback or entire show requester)
        """

        movie_requesters: dict[str, set[str]] = {}
        tv_season_requesters: dict[tuple[str, int], set[str]] = {}
        tv_show_requesters: dict[str, set[str]] = {}

        for req in requests_list:
            media: dict[str, Any] = req.get("media", {}) or {}
            requested_by: dict[str, Any] = req.get("requestedBy", {}) or {}
            user_id = requested_by.get("id")
            username = (
                requested_by.get("displayName")
                or requested_by.get("username")
                or requested_by.get("plexUsername")
                or (f"user#{user_id}" if user_id is not None else UNKNOWN_REQUESTER)
            )

            media_type: str | None = media.get("mediaType")
            tmdb_id = media.get("tmdbId")
            tvdb_id = media.get("tvdbId")

            if media_type == MEDIA_TYPE_MOVIE and tmdb_id:
                movie_requesters.setdefault(str(tmdb_id), set()).add(username)
            elif media_type == _SEERR_MEDIA_TYPE_TV and tvdb_id:
                tvdb_key = str(tvdb_id)
                tv_show_requesters.setdefault(tvdb_key, set()).add(username)
                seasons_list: list[dict[str, Any]] = req.get("seasons", []) or []
                for season in seasons_list:
                    season_number: int | None = season.get("seasonNumber")
                    if season_number is not None:
                        tv_season_requesters.setdefault(
                            (tvdb_key, season_number), set()
                        ).add(username)

        def collapse(d: dict[Any, set[str]]) -> dict[Any, str]:
            return {k: ", ".join(sorted(v)) for k, v in d.items()}

        return RequesterMaps(
            movies=collapse(movie_requesters),
            tv_seasons=collapse(tv_season_requesters),
            tv_shows=collapse(tv_show_requesters),
        )


#################################################
# Tautulli Client
#################################################
@dataclass
class TautulliClient:
    """client for reading data from tautulli"""

    url: str
    api_key: str = field(repr=False)
    session: requests.Session = field(
        init=False, default_factory=requests.Session, repr=False
    )
    verify_ssl: bool = True
    endpoint: str = ""

    def __post_init__(self):
        self.url = self.url.rstrip("/")
        self.endpoint = f"{self.url}/api/v2"

    def _call(self, cmd: str, **params: Any) -> Any:
        query: dict[str, Any] = {"apikey": self.api_key, "cmd": cmd, **params}
        response = self.session.get(
            self.endpoint, params=query, verify=self.verify_ssl, timeout=API_TIMEOUT_SEC
        )
        response.raise_for_status()
        data = response.json()

        result = data.get("response", {})
        if result.get("result") != "success":
            raise RuntimeError(
                f"Tautulli API error on '{cmd}': {result.get('message')}"
            )

        return result.get("data", {})

    def get_libraries(self) -> list[dict[str, Any]]:
        """get libraries"""
        return self._call("get_libraries")

    def get_metadata(self, rating_key: str) -> dict[str, Any]:
        """full meta data for item - need to call for guid to link seerr data"""
        return self._call("get_metadata", rating_key=rating_key)

    def get_history(
        self,
        parent_rating_key: str,
        length: int = 1,
    ) -> dict[str, Any]:
        """
        most recent play history for an item's children, e.g. a season's episodes.
        get_library_media_info never populates last_played/play_count for season
        rows, so season-level watch stats have to come from here instead.
        """
        return self._call(
            "get_history",
            parent_rating_key=parent_rating_key,
            order_column="date",
            order_dir="desc",
            start=0,
            length=length,
        )

    def get_library_media_info(
        self,
        section_id: str | None = None,
        rating_key: str | None = None,
        start: int = 0,
        length: int = 500,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """get media based on section or rating key"""

        params: dict[str, Any] = {
            "order_column": "added_at",
            "order_dir": "asc",
            "start": start,
            "length": length,
        }

        if section_id is not None:
            params["section_id"] = section_id
        if rating_key is not None:
            params["rating_key"] = rating_key
        if refresh:
            # Tautulli's library_media_info table can hold an orphaned rating_key
            # for an item after Plex reassigns it one (e.g. a rematch) - refresh
            # forces a live resync from Plex instead of reading that stale table.
            params["refresh"] = "true"

        return self._call("get_library_media_info", **params)

    def iter_items(
        self,
        section_id: str | None = None,
        rating_key: str | None = None,
        page_size: int = 500,
        refresh: bool = False,
    ) -> Generator[Any, None, None]:
        """
        yield every row, handle pagination
        Pass section id to list whole library or rating_key for show to list show seasons
        """

        start = 0
        first_page = True
        while True:
            page: dict[str, Any] = self.get_library_media_info(
                section_id=section_id,
                rating_key=rating_key,
                start=start,
                length=page_size,
                # only force the resync once per call - the underlying table
                # is synced for every page after that
                refresh=refresh and first_page,
            )
            first_page = False
            rows: list[Any] = page.get("data", [])
            if not rows:
                return
            yield from rows

            start += len(rows)
            if len(rows) < page_size:
                return
