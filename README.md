# plex-library-watch-history

> [!NOTE]
> While working on this I found [Tracearr](https://github.com/connorgallopo/tracearr) which covers most of what I was looking to do here. Because of that, I doubt there will be many updates to this as I test out and use Tracearr instead.

A command-line tool that reports on unwatched and stale media in a Plex library.

## Features

- Lists movies and TV shows that have never been watched, based on how long ago they were added.
- Lists movies and TV shows that haven't been watched recently, based on last play date.
- Can report at the season level instead of the whole show.
- Looks up the requester for each item from Seerr, if configured.
- Prints a per-requester summary (never watched / stale / total counts).
- Can export results to a CSV file.
- Caches Tautulli season lookups and Seerr request data locally to speed up repeat runs.

## Requirements

- Python 3.14 or newer
- A running Tautulli instance with an API key
- (Optional) A Seerr instance with an API key (if you want requester data)

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync
```

## Configuration

Update `config.toml` with your own values.

```toml
days_unwatched = 180
library_names = []
season_level = false
sort_by = 'title'
sort_order = 'asc'
include_never_watched = true
include_stale_watched = true

[tautulli]
url = 'http://your-tautulli-host:8181/'
api_key = 'your-tautulli-api-key'
verify_ssl = true

[seerr]
url = 'http://your-seerr-host:5055/'
api_key = 'your-seerr-api-key'
verify_ssl = true

[cache]
cache_enabled = true
cache_file = '.cache/tautulli_report_cache.json'
seer_cache_ttl_hours = 1
```

`tautulli.url` and `tautulli.api_key` are required. The `[seerr]` section is optional. If `seerr.url` and `seerr.api_key` are left blank, requesters are reported as "Unknown".

Run `uv run main.py --help` to see additional config values. Command-line flags take priority
over the config file.

## Usage

```bash
uv run main.py [options]
```

Run with no arguments to use the values from `config.toml`. Available options:

| Flag | Default | Description |
| --- | --- | --- |
| `--days-unwatched INT` | 180 | Minimum age, in days, before an item counts as never watched or stale. |
| `--library-names NAME [NAME ...]` | all libraries | Restrict the report to specific Tautulli library names. |
| `--season-level` / `--no-season-level` | off | Report on individual TV seasons instead of whole shows. |
| `--sort-by {title,last_watched,requester}` | title | Field to sort results by. |
| `--sort-order {asc,desc}` | asc | Sort direction. |
| `--group-by {none,requester}` | none | Group console output by requester. |
| `--include-never-watched` / `--no-include-never-watched` | on | Include items that have never been played. |
| `--include-stale-watched` / `--no-include-stale-watched` | on | Include items that were played but not recently. |
| `--include-unknown-requester` / `--no-include-unknown-requester` | on | Include items with no known requester. |
| `--export-csv PATH` | none | Also write the results to a CSV file at this path. |
| `--refresh-cache` / `--no-refresh-cache` | off | Clear the local cache before running. |
| `--disable-cache` / `--no-disable-cache` | off | Skip reading and writing the local cache for this run. |

Run `uv run main.py --help` to see this from the tool itself.

### Examples

Report on items untouched for a year, grouped by requester:

```bash
uv run main.py --days-unwatched 365 --group-by requester
```

Report on a single library and export the results to CSV:

```bash
uv run main.py --library-names "Movies" --export-csv out.csv
```

## Output

The report prints to the console in three parts:

1. A summary table of never-watched and stale counts per requester.
2. The list of never-watched items.
3. The list of stale (watched but not recently) items.

If `--export-csv` is given, the same data is also written to a CSV file with one row per item.

## Caching

To avoid re-querying Tautulli and Seerr on every run, the tool caches:

- Season listings per show, invalidated automatically if a show's added date, last played date or play count changes.
- The full Seerr request list, refreshed after `seer_cache_ttl_hours` hours.

The cache is stored as JSON at the path set by `cache.cache_file` (default
`.cache/tautulli_report_cache.json`). Use `--refresh-cache` to force a clean fetch, or
`--disable-cache` to bypass the cache entirely for one run.

## Logs

Logs are written to the console and to `logs/main.log`

## TODO

- [ ] improve speed/concurrent calls
  - add a requests.Session() stored on class to reuse
- [ ] use rich or other console output to make output easier to read
- [ ] tests

## License

MIT. See [LICENSE](LICENSE).
