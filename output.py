"""output.py"""

import csv
import logging
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from models import (
    STATUS_NEVER_WATCHED,
    STATUS_STALE_WATCHED,
    GroupBy,
    MediaItem,
    Status,
)

logger = logging.getLogger(__name__)


def requester_summary(
    never_watched: list[MediaItem], stale_watched: list[MediaItem]
) -> list[tuple[str, int, int, int]]:
    """return list of (requester, never, stale, total) sorted by total"""
    never = Counter(item.requester for item in never_watched)
    stale = Counter(item.requester for item in stale_watched)
    names = never.keys() | stale.keys()
    rows = [(n, never[n], stale[n], never[n] + stale[n]) for n in names]
    rows.sort(key=lambda r: (-r[3], r[0].lower()))
    return rows


def print_console_end(console: Console):
    console.rule(characters="=")


def print_console_header(console: Console, header: str):
    console.rule(f"[sky_blue1]{header}")


_GROUP_KEY_FNS: dict[str, Callable[[MediaItem], str]] = {
    "requester": lambda item: item.requester,
    "media_type": lambda item: item.media_type,
}


def group_items(
    items: list[MediaItem], group_by: GroupBy | None
) -> dict[str, list[MediaItem]]:
    """Split items into named groups. A single "" -> items entry means "don't group"."""
    key_fn = _GROUP_KEY_FNS.get(group_by) if group_by is not None else None
    if key_fn is None:
        return {"": items}

    groups: dict[str, list[MediaItem]] = defaultdict(list)
    for item in items:
        groups[key_fn(item)].append(item)

    return dict(sorted(groups.items(), key=lambda kv: kv[0].lower()))


def _build_item_table() -> Table:
    table = _build_summary_table()
    table.add_column("Requester", style="green")
    table.add_column("Title", style="magenta")
    table.add_column("Type", style="yellow")
    table.add_column("Added", justify="right", style="cyan", no_wrap=True)
    table.add_column("Last Watched", justify="left", style="cyan", no_wrap=True)
    return table


def _build_summary_table() -> Table:
    return Table(box=box.DOUBLE_EDGE)


def _add_item_row(table: Table, item: MediaItem) -> None:
    added_at = item.added_at.strftime("%B %d, %Y") if item.added_at else "Unknown"
    last_played = (
        item.last_played.strftime("%B %d, %Y") if item.last_played else "Never"
    )
    # only requester and display title need the Text wraopper
    table.add_row(
        Text(item.requester),
        Text(item.display_title),
        item.media_type,
        added_at,
        last_played,
    )


def print_table(
    console: Console,
    items: list[MediaItem],
    status: Status,
    group_by: GroupBy | None,
    days: int,
) -> None:
    title = (
        f"NEVER WATCHED (added {days}+ days ago, 0 plays)"
        if status == STATUS_NEVER_WATCHED
        else f"STALE (last watched {days}+ days ago)"
    )

    if not items:
        print_console_header(console, title)
        console.print("[bold green]No items to report![/bold green]")
        print_console_end(console)
        return

    print_console_header(console, title)

    for group_name, group_rows in group_items(items, group_by).items():
        if group_name:
            console.print(Text(group_name, style="bold"))

        table = _build_item_table()
        for item in group_rows:
            _add_item_row(table, item)
        console.print(table)

    print_console_end(console)


def print_report(
    never_watched: list[MediaItem],
    stale_watched: list[MediaItem],
    days: int,
    group_by: GroupBy | None,
) -> None:
    summary = requester_summary(never_watched, stale_watched)

    console = Console()
    header = f"REQUEST SUMMARY (not watched within {days} days)"
    if summary:
        print_console_header(console, header)
        table = _build_summary_table()
        table.add_column("Requester", style="green")
        table.add_column("Never", style="red", justify="right")
        table.add_column("Stale", style="yellow", justify="right")
        table.add_column("Total", style="magenta", justify="right")

        # only need text wrapper on name
        for name, nc, sc, total in summary:
            table.add_row(Text(name), str(nc), str(sc), str(total))

        console.print(table)
    else:
        print_console_header(console, header)
        console.print("[bold green]No items to report![/bold green]")
    print_console_end(console)

    print_table(console, never_watched, STATUS_NEVER_WATCHED, group_by, days)
    print_table(console, stale_watched, STATUS_STALE_WATCHED, group_by, days)


def _csv_row(
    item: MediaItem, status: Status, when: datetime | None
) -> list[str | int | None]:
    return [
        status,
        item.title,
        item.season_number,
        item.media_type,
        item.library_name,
        when.strftime("%Y-%m-%d") if when else "",
        item.play_count,
        item.requester,
        item.rating_key,
    ]


def export_csv(
    path: Path, never_watched: list[MediaItem], stale_watched: list[MediaItem]
):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "status",
                "title",
                "season",
                "media_type",
                "library",
                "last_played_or_added",
                "play_count",
                "requester",
                "rating_key",
            ]
        )
        for item in never_watched:
            writer.writerow(_csv_row(item, STATUS_NEVER_WATCHED, item.added_at))
        for item in stale_watched:
            writer.writerow(_csv_row(item, STATUS_STALE_WATCHED, item.last_played))

    logger.info("Output written to CSV file: %s", path)
