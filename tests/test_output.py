import csv
import io
from datetime import datetime, timezone

from rich.console import Console

from models import STATUS_NEVER_WATCHED, STATUS_STALE_WATCHED
from output import (
    _add_item_row,
    _build_item_table,
    _build_summary_table,
    _csv_row,
    export_csv,
    group_items,
    print_console_end,
    print_console_header,
    print_report,
    print_table,
    requester_summary,
)


def _console():
    return Console(file=io.StringIO(), width=200)


#################################################
# requester_summary
#################################################
def test_requester_summary_counts_and_sorts(make_media_item):
    never = [make_media_item(requester="Bob"), make_media_item(requester="Alice")]
    stale = [make_media_item(requester="Bob")]
    rows = requester_summary(never, stale)
    assert rows == [("Bob", 1, 1, 2), ("Alice", 1, 0, 1)]


def test_requester_summary_empty():
    assert requester_summary([], []) == []


#################################################
# console helpers
#################################################
def test_print_console_header_and_end():
    console = _console()
    print_console_header(console, "My Header")
    print_console_end(console)
    out = console.file.getvalue()
    assert "My Header" in out
    assert "=" in out


#################################################
# group_items
#################################################
def test_group_items_no_grouping_returns_single_bucket(make_media_item):
    items = [make_media_item(), make_media_item()]
    assert group_items(items, None) == {"": items}


def test_group_items_by_requester(make_media_item):
    a = make_media_item(requester="Alice")
    b = make_media_item(requester="Bob")
    grouped = group_items([a, b], "requester")
    assert grouped == {"Alice": [a], "Bob": [b]}


def test_group_items_by_media_type_sorted_case_insensitive(make_media_item):
    a = make_media_item(media_type="show")
    b = make_media_item(media_type="Movie")
    grouped = group_items([a, b], "media_type")
    assert list(grouped.keys()) == ["Movie", "show"]


#################################################
# table building
#################################################
def test_build_item_table_columns():
    table = _build_item_table()
    headers = [col.header for col in table.columns]
    assert headers == ["Requester", "Title", "Type", "Added", "Last Watched"]


def test_build_summary_table_has_no_columns_yet():
    table = _build_summary_table()
    assert table.columns == []


def test_add_item_row_with_dates(make_media_item):
    table = _build_item_table()
    added = datetime(2024, 1, 15, tzinfo=timezone.utc)
    watched = datetime(2024, 2, 20, tzinfo=timezone.utc)
    item = make_media_item(added_at=added, last_played=watched, requester="Alice")
    _add_item_row(table, item)
    console = _console()
    console.print(table)
    out = console.file.getvalue()
    assert "January 15, 2024" in out
    assert "February 20, 2024" in out
    assert "Alice" in out


def test_add_item_row_without_dates(make_media_item):
    table = _build_item_table()
    item = make_media_item(added_at=None, last_played=None)
    _add_item_row(table, item)
    console = _console()
    console.print(table)
    out = console.file.getvalue()
    assert "Unknown" in out
    assert "Never" in out


#################################################
# print_table
#################################################
def test_print_table_empty_shows_no_items_message():
    console = _console()
    print_table(console, [], STATUS_NEVER_WATCHED, None, days=180)
    out = console.file.getvalue()
    assert "NEVER WATCHED" in out
    assert "No items to report!" in out


def test_print_table_stale_title():
    console = _console()
    print_table(console, [], STATUS_STALE_WATCHED, None, days=90)
    out = console.file.getvalue()
    assert "STALE (last watched 90+ days ago)" in out


def test_print_table_grouped_shows_group_headers(make_media_item):
    console = _console()
    items = [make_media_item(requester="Alice", title="A"), make_media_item(requester="Bob", title="B")]
    print_table(console, items, STATUS_NEVER_WATCHED, "requester", days=180)
    out = console.file.getvalue()
    assert "Alice" in out
    assert "Bob" in out


#################################################
# print_report (uses its own internal Console -> captured via capsys)
#################################################
def test_print_report_with_no_items(capsys):
    print_report([], [], days=180, group_by=None)
    out = capsys.readouterr().out
    assert "REQUEST SUMMARY" in out
    assert "No items to report!" in out


def test_print_report_with_items(capsys, make_media_item):
    never = [make_media_item(title="Never Watched Movie", requester="Alice")]
    stale = [
        make_media_item(
            title="Stale Movie",
            requester="Bob",
            play_count=2,
            last_played=datetime.now(timezone.utc),
        )
    ]
    print_report(never, stale, days=180, group_by=None)
    out = capsys.readouterr().out
    assert "Never Watched Movie" in out
    assert "Stale Movie" in out
    assert "Alice" in out
    assert "Bob" in out


#################################################
# CSV export
#################################################
def test_csv_row_shape(make_media_item):
    when = datetime(2024, 3, 1, tzinfo=timezone.utc)
    item = make_media_item(
        title="T", season_number=2, rating_key="55", requester="Alice", play_count=3
    )
    row = _csv_row(item, STATUS_STALE_WATCHED, when)
    assert row == [
        STATUS_STALE_WATCHED,
        "T",
        2,
        item.media_type,
        item.library_name,
        "2024-03-01",
        3,
        "Alice",
        "55",
    ]


def test_csv_row_no_date_is_blank(make_media_item):
    item = make_media_item()
    row = _csv_row(item, STATUS_NEVER_WATCHED, None)
    assert row[5] == ""


def test_export_csv_writes_expected_rows(tmp_path, make_media_item):
    never = [make_media_item(title="Never Item", added_at=datetime(2024, 1, 1, tzinfo=timezone.utc))]
    stale = [
        make_media_item(
            title="Stale Item",
            play_count=1,
            last_played=datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
    ]
    out_path = tmp_path / "out.csv"
    export_csv(out_path, never, stale)

    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == [
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
    assert rows[1][0] == STATUS_NEVER_WATCHED
    assert rows[1][1] == "Never Item"
    assert rows[2][0] == STATUS_STALE_WATCHED
    assert rows[2][1] == "Stale Item"
