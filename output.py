import csv
import logging
from collections import defaultdict
from pathlib import Path

from models import MediaItem

logger = logging.getLogger(__name__)


def requester_summary(never_watched: list[MediaItem], stale_watched: list[MediaItem]):
    """return list of (requester, never, stale, total) sorted by total"""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item in never_watched:
        counts[item.requester][0] += 1
    for item in stale_watched:
        counts[item.requester][1] += 1

    rows = [(name, nc, sc, nc + sc) for name, (nc, sc) in counts.items()]
    rows.sort(key=lambda r: (-r[3], r[0].lower()))
    return rows


def group_by_requester(items: list[MediaItem]) -> dict[str, list[MediaItem]]:
    groups: dict[str, list[MediaItem]] = defaultdict(list)
    for item in items:
        groups[item.requester].append(item)

    return dict(sorted(groups.items(), key=lambda kv: kv[0].lower()))


def format_line(item: MediaItem, status: str) -> str:
    when_str = ""
    if status == "never_watched":
        when_str = (
            f"Never watched (added {item.added_at.strftime('%B %d, %Y')})"
            if item.added_at
            else "Never watched"
        )
    else:
        when_str = (
            item.last_played.strftime("%B %d, %Y") if item.last_played else "Unknown"
        )

    return f"{item.display_title} - {when_str} - {item.requester}"


def print_section(items: list[MediaItem], status: str, group_by: str, days: int):
    header = (
        f"NEVER WATCHED (added {days}+ days ago, 0 plays)"
        if status == "never_watched"
        else f"STALE (lasted watched {days}+ days ago)"
    )
    print(f"\n*** {header} ***")

    if not items:
        print("NONE!")
        return

    if group_by == "requester":
        for name, group_items in group_by_requester(items).items():
            print(f"  -- {name} --")
            for item in group_items:
                print(f"  {format_line(item, status)}")
    else:
        for item in items:
            print(format_line(item, status))


def print_report(
    never_watched: list[MediaItem],
    stale_watched: list[MediaItem],
    days: int,
    group_by: str,
) -> None:
    summary = requester_summary(never_watched, stale_watched)
    print("\n*** REQUEST SUMMARY (not watched within {days} days) ***")
    if summary:
        print(f"{'Requester':<25} {'Never Watched':>14} {'Stale':>8} {'Total':>8}")

        for name, nc, sc, total in summary:
            print(f"{name:<25} {nc:>14} {sc:>8} {total:>8}")
    else:
        print("NONE!")

    print_section(never_watched, "never_watched", group_by, days)
    print_section(stale_watched, "stale_watched", group_by, days)


def export_csv(
    path: Path, never_watched: list[MediaItem], stale_watched: list[MediaItem]
):
    with path.open("w", newline="") as f:
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
            when = item.added_at.strftime("%Y-%m-%d") if item.added_at else ""
            writer.writerow(
                [
                    "never_watched",
                    item.title,
                    item.season_number,
                    item.media_type,
                    item.library_name,
                    when,
                    item.play_count,
                    item.requester,
                    item.rating_key,
                ]
            )
        for item in stale_watched:
            when = item.last_played.strftime("%Y-%m-%d") if item.last_played else ""
            writer.writerow(
                [
                    "stale_watched",
                    item.title,
                    item.season_number,
                    item.media_type,
                    item.library_name,
                    when,
                    item.play_count,
                    item.requester,
                    item.rating_key,
                ]
            )

    logger.info("Output written to CSV file: %s", path)
