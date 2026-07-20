"""Report unwatched or stale Plex items via Tautulli.

Settings load in layers, highest to lowest priority: CLI args ->
config.toml -> field defaults. Unset CLI flags fall through to the TOML
value automatically, so there's no `args.x if args.x else settings.x`
merge step to maintain by hand.

Run: `uv run main.py --help`
"""

import logging
import logging.handlers
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cache import Cache
from clients import SeerrClient, TautulliClient
from models import UNKNOWN_REQUESTER, UNKNOWN_TITLE, MediaItem
from output import export_csv, print_report
from settings import ConnectionSettings, ReportSettings

_NEW_AGENT_PREFIXES = {"tmdb://": "tmdb_id", "tvdb://": "tvdb_id"}
_LEGACY_AGENT_PATTERNS = {
    "tmdb_id": re.compile(r"com\.plexapp\.agents\.themoviedb://(\d+)"),
    "tvdb_id": re.compile(r"com\.plexapp\.agents\.thetvdb://(\d+)"),
}

#############################################
# Logging
#############################################
logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "main.log"
LOG_FILES_TO_KEEP = 5
LOG_MAX_BYTES = 1_000_000


def _configure_logging() -> None:
    """Log to the console and to logs/main.log"""
    LOG_DIR.mkdir(exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_FILES_TO_KEEP - 1
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), file_handler],
    )


def _to_datetime(epoch_val: str | None) -> datetime | None:
    """clean up tautulli times"""
    if not epoch_val:
        return None
    try:
        epoch_int = int(epoch_val)
    except TypeError, ValueError:
        return None
    if epoch_int <= 0:
        return None
    return datetime.fromtimestamp(epoch_int, tz=timezone.utc)


def make_sort_key(sort_by: str):
    """clean up sort key for never watched items"""
    epoch_min = datetime.min.replace(tzinfo=timezone.utc)

    def key(item: MediaItem):
        if sort_by == "last_watched":
            date = item.last_played or item.added_at or epoch_min
            return (date, item.title.lower(), item.season_number or 0)

        if sort_by == "requester":
            return (item.requester.lower(), item.title.lower(), item.season_number or 0)

        return (item.title.lower(), item.season_number or 0)

    return key


def categorize_watches(
    items: list[MediaItem],
    days: int,
    sort_by: str,
    sort_order: str,
    include_unknown: bool,
) -> tuple[list[MediaItem], list[MediaItem]]:
    """sort stale and watch history"""
    never_watched: list[MediaItem] = []
    stale_watched: list[MediaItem] = []

    for item in items:
        if not include_unknown and item.requester == UNKNOWN_REQUESTER:
            continue
        if item.play_count == 0:
            if item.days_since_added is not None and item.days_since_added >= days:
                never_watched.append(item)
        else:
            if item.days_since_watched is not None and item.days_since_watched >= days:
                stale_watched.append(item)

    key_fn = make_sort_key(sort_by)
    reverse: bool = sort_order == "desc"
    never_watched.sort(key=key_fn, reverse=reverse)
    stale_watched.sort(key=key_fn, reverse=reverse)
    return never_watched, stale_watched


def get_single_requester(
    item: MediaItem,
    movie_requesters: dict[Any, Any],
    tv_season_requesters: dict[Any, Any],
    tv_show_requesters: dict[Any, Any],
) -> str:
    """Look up the requester via the id maps built from seerr request list."""

    if item.media_type == "movie":
        return movie_requesters.get(item.moviedb_id, UNKNOWN_REQUESTER)

    # TV show or season
    if item.season_number is not None:
        key = (item.tvdb_id, item.season_number)
        if key in tv_season_requesters:
            return tv_season_requesters[key]
    return tv_show_requesters.get(item.tvdb_id, UNKNOWN_REQUESTER)


def get_requesters(
    cache: Cache,
    url: str,
    api_key: str,
    ttl: int | None,
    verify_ssl: bool = True,
):
    """if using seerr, find who requested"""

    cached_requests = cache.get_seerr_requests(ttl) if ttl else None
    if cached_requests is not None:
        logger.info("Using cached Seerr requests")
        requests_list = cached_requests
    else:
        logger.info("Fetching data from Seerr...")
        seerr = SeerrClient(url=url, api_key=api_key, verify_ssl=verify_ssl)
        requests_list = seerr.fetch_all_requests()
        cache.set_seerr_requests(requests_list)

    return SeerrClient.build_maps_from_requests(requests_list)


def _guid_id(guid: Any) -> str:
    """guids[] entry is a dict for the new agent or a bare string for the legacy one."""
    return str(guid.get("id", "")) if hasattr(guid, "get") else str(guid)


def extract_external_ids(metadata: dict[str, Any]) -> tuple[str, str]:
    """
    get tmdb and tvdb ids from a get_metadata response.
    try for new agent guids list first fallback to legacy
    """
    ids = {"tmdb_id": "", "tvdb_id": ""}
    guids: list[Any] = metadata.get("guids", []) or []
    for guid in guids:
        gid = _guid_id(guid)
        for prefix, key in _NEW_AGENT_PREFIXES.items():
            if gid.startswith(prefix):
                ids[key] = gid.removeprefix(prefix)

    if not ids["tmdb_id"] and not ids["tvdb_id"]:
        legacy_guid = metadata.get("guid", "") or ""
        for key, pattern in _LEGACY_AGENT_PATTERNS.items():
            if match := pattern.search(legacy_guid):
                ids[key] = match.group(1)

    return ids["tmdb_id"], ids["tvdb_id"]


def fetch_external_ids(
    client: TautulliClient, rating_key: str, cache: Cache | None
) -> tuple[str, str]:
    """get tmdb or tvdb id for media item. check cache first otherwise call tautulli endpoint"""
    if cache:
        cached = cache.get_external_ids(rating_key)
        if cached is not None:
            return cached

    metadata = client.get_metadata(rating_key)
    tmdb_id, tvdb_id = extract_external_ids(metadata)

    if cache:
        cache.set_external_ids(rating_key, tmdb_id, tvdb_id)

    return tmdb_id, tvdb_id


def fetch_media_items(
    client: TautulliClient,
    library_names: list[str],
    movie_requesters: dict[Any, Any],
    tv_season_requesters: dict[Any, Any],
    tv_show_requesters: dict[Any, Any],
    season_level: bool = False,
    cache: Cache | None = None,
) -> list[MediaItem]:
    """build out and return list of media items"""

    libraries = client.get_libraries()
    # filter to just movie/shows
    libraries = [
        lib for lib in libraries if lib.get("section_type") in ("movie", "show")
    ]

    if library_names:
        wanted = {name.lower() for name in library_names}
        libraries = [
            lib for lib in libraries if lib.get("section_name", "").lower() in wanted
        ]

    items: list[MediaItem] = []

    for lib in libraries:
        section_id = lib["section_id"]
        section_name = lib["section_name"]
        section_type = lib["section_type"]

        logger.info("Scanning library: %s (%s)...", section_name, section_type)

        for row in client.iter_items(section_id=section_id):
            row_media_type = row.get("media_type", section_type)
            rating_key = str(row.get("rating_key", ""))

            # fetch guid ids for matching to seerr data
            tmdb_id, tvdb_id = fetch_external_ids(client, rating_key, cache)

            if row_media_type == "show" and season_level:
                show_title = row.get("title", UNKNOWN_TITLE)

                season_rows = cache.get_show_seasons(rating_key, row) if cache else None
                if season_rows is None:
                    season_rows = list(client.iter_items(rating_key=rating_key))
                    if cache:
                        cache.set_show_seasons(rating_key, row, season_rows)

                for season_row in season_rows:
                    if season_row.get("media_type") != "season":
                        continue
                    item = MediaItem(
                        title=show_title,
                        media_type="season",
                        library_name=section_name,
                        rating_key=str(season_row.get("rating_key", "")),
                        added_at=_to_datetime(season_row.get("added_at")),
                        last_played=_to_datetime(season_row.get("last_played")),
                        play_count=int(season_row.get("play_count") or 0),
                        tvdb_id=tvdb_id,
                        season_number=int(season_row.get("media_index") or 0),
                    )
                    item.requester = get_single_requester(
                        item, movie_requesters, tv_season_requesters, tv_show_requesters
                    )
                    items.append(item)
                continue

            # movie or whole show
            item = MediaItem(
                title=row.get("title", UNKNOWN_TITLE),
                media_type=row_media_type,
                library_name=section_name,
                rating_key=str(row.get("rating_key", "")),
                added_at=_to_datetime(row.get("added_at")),
                last_played=_to_datetime(row.get("last_played")),
                play_count=int(row.get("play_count") or 0),
                moviedb_id=tmdb_id,
                tvdb_id=tvdb_id,
            )

            item.requester = get_single_requester(
                item, movie_requesters, tv_season_requesters, tv_show_requesters
            )
            items.append(item)

    return items


def main():
    """main.py"""

    _configure_logging()

    config = ConnectionSettings()  # TOML only -- no CLI source configured
    report = ReportSettings()  # cli_parse_args=True parses sys.argv here
    logger.info("Loaded Config file: %s", config)
    logger.info("Loaded report settings: %s", report)

    days = report.days_unwatched
    season_level = report.season_level
    library_names = report.library_names
    cache_enabled = not report.disable_cache and config.cache.cache_enabled
    logger.info("cache_enabled=%s", cache_enabled)

    movie_requesters, tv_season_requesters, tv_show_requesters = {}, {}, {}
    # define the clients needed
    tautulli_url, tautulli_api_key = config.tautulli.require_configured("Tautulli")
    tautulli = TautulliClient(
        url=tautulli_url,
        api_key=tautulli_api_key,
        verify_ssl=config.tautulli.verify_ssl,
    )

    cache = Cache(config.cache.cache_file, cache_enabled)
    if report.refresh_cache:
        cache.clear()

    if config.seerr.api_key and config.seerr.url:
        movie_requesters, tv_season_requesters, tv_show_requesters = get_requesters(
            cache,
            config.seerr.url,
            config.seerr.api_key,
            config.cache.seer_cache_ttl_hours,
            config.seerr.verify_ssl,
        )
    else:
        logger.info("Seerr not configured - requester will show as 'Unknown'")

    logger.info(
        "Fetching library data from Tautulli (days=%s, season_level=%s)",
        days,
        season_level,
    )
    items = fetch_media_items(
        tautulli,
        library_names,
        movie_requesters,
        tv_season_requesters,
        tv_show_requesters,
        season_level,
        cache,
    )

    if cache_enabled:
        logger.info(
            "External id cached: %s hits, %s fetched fresh",
            cache.ext_hits,
            cache.ext_misses,
        )
        if season_level:
            logger.info(
                "Season cache: %s hits, %s misses fetched fresh",
                cache.hits,
                cache.misses,
            )
        cache.save()

    never_watched, stale_watched = categorize_watches(
        items, days, report.sort_by, report.sort_order, report.include_unknown_requester
    )

    if not report.include_never_watched:
        never_watched = []
    if not report.include_stale_watched:
        stale_watched = []

    print_report(never_watched, stale_watched, days, str(report.group_by))

    if report.export_csv:
        export_csv(report.export_csv, never_watched, stale_watched)


if __name__ == "__main__":
    main()
