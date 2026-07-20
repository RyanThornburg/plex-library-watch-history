# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CLI tool that reports unwatched and stale media in a Plex library, using Tautulli as the
data source (and optionally Seerr to attribute each item to the user who requested it).

## Commands

```bash
uv sync                          # install/update dependencies
uv run main.py                   # run with config.toml values
uv run main.py --help            # see all CLI flags
uvx pyright                      # type check
```

There is no test suite and no linter config yet (see README TODO list).

Run a single module's syntax/import quickly with e.g. `uv run python -c "import cache"` rather
than invoking main.py end-to-end, since main.py requires a reachable Tautulli instance.

## Python version — read before flagging syntax

This project targets **Python 3.14+** (`requires-python = ">=3.14"` in pyproject.toml,
`.python-version` pins `3.14`) and uses **PEP 758** syntax: bare `except` clauses with multiple
exception types and no parentheses, e.g. `except TypeError, ValueError:` or
`except json.JSONDecodeError, OSError:` (see `main.py`, `cache.py`). This is valid Python 3.14
syntax, not a Python 2 leftover — do not "fix" it by adding parentheses, and do not flag it as a
syntax error. Always check behavior against 3.14 semantics, not whatever `python3` resolves to
on the host.

## Architecture

Data flows in one direction through five modules, wired together in `main.py`:

```
settings.py -> clients.py -> main.py -> models.py -> output.py
                  ^                          |
                  |-------- cache.py --------|
```

- **settings.py** — two separate `pydantic-settings` classes, not one, because they have
  different priority chains:
  - `ConnectionSettings` (Tautulli/Seerr URLs, API keys, cache config): TOML-only, sourced from
    `config.toml`. Never accepts CLI args — credentials shouldn't be typeable on a command line.
  - `ReportSettings` (day thresholds, sort/group options, CSV export flags): CLI args override
    `config.toml` values, which override field defaults. Because `cli_parse_args=True` is used,
    just running `ReportSettings()` parses `sys.argv`.
  - Both classes override `settings_customise_sources` to layer TOML under whichever
    higher-priority sources pydantic-settings supplies. There's no manual
    `args.x if args.x else settings.x` merge logic anywhere — that fallthrough is what
    pydantic-settings' source layering buys you.

- **clients.py** — thin `requests`-based clients for the two external APIs. `TautulliClient` and
  `SeerrClient` each expose an `iter_*` generator that handles pagination transparently. Note the
  vocabulary mismatch between the two systems: Tautulli calls a TV item `"show"`, Seerr calls it
  `"tv"` — both `models.py` and `clients.py` have comments pointing at each other about this, and
  the media-type constants in `models.py` (`MEDIA_TYPE_*`) are Tautulli's vocabulary.

- **models.py** — plain dataclasses (`MediaItem`, `RequesterMaps`) and the `Literal` type
  aliases used across the CLI surface (`SortBy`, `SortOrder`, `GroupBy`, `Status`). No behavior
  beyond a few derived properties on `MediaItem` (`display_title`, `days_since_added`,
  `days_since_watched`).

- **cache.py** — a single JSON file (`config.toml`'s `cache.cache_file`) holding two independent
  caches with different invalidation strategies:
  - Per-show season listings, keyed by rating key, invalidated by a fingerprint
    (`added_at`/`last_played`/`play_count`) rather than a TTL — if the fingerprint hasn't
    changed, Tautulli wouldn't return anything new.
  - The full Seerr request list, invalidated by a TTL (`seer_cache_ttl_hours`).
  - Also caches per-item tmdb/tvdb external IDs (`get_metadata` lookups), which never expire
    since a rating key's identity doesn't change once matched.
  - Cache failures are designed to degrade to a live fetch, not raise — see the class docstring.

- **main.py** — orchestration: builds the clients and cache from settings, walks libraries ->
  items (optionally expanding TV shows into per-season `MediaItem`s when `season_level` is set),
  looks up each item's requester via `RequesterMaps` built from Seerr, buckets items into
  never-watched vs. stale via `categorize_watches`, then hands the result to `output.py`.
  `extract_external_ids`/`_guid_id` handle the fact that Plex's `guids[]` metadata field differs
  in shape between the new agent (list of dicts with prefixed IDs like `tmdb://123`) and the
  legacy agent (a single string matched with regex).

- **output.py** — all presentation: Rich tables/console output (`print_report`) and CSV export
  (`export_csv`). Both consume the same `never_watched`/`stale_watched` lists produced by
  `main.py`; there's no separate data-shaping step here.

## config.toml

`config.toml` holds live Tautulli/Seerr URLs and API keys and is intentionally git
skip-worktree'd (`git update-index --skip-worktree`) so local credentials never show up in `git
status`/`git diff`. Don't `git add -f` it, and don't run `git diff`/`git status` fixes that would
try to reconcile it.
