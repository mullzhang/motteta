"""Human-readable views of acquisition records."""

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

FORMATS = {"print": "Print", "digital": "Digital", "unknown": "Unknown"}
POSSESSION = {"owned": "Owned", "disposed": "Disposed", "gift": "Gift", "unknown": "Unknown"}
ORDER_STATES = {
    "completed": "Completed",
    "ordered": "Ordered",
    "preordered": "Preordered",
    "cancelled": "Cancelled",
    "returned": "Returned",
    "unknown": "Unknown",
    None: "N/A",
}
CHECK_LABELS = {
    "記録あり": "Record found",
    "記録なし": "No record",
    "確認できません": "Unable to identify",
    "同じ本の可能性あり": "Possible match",
}


def print_records(records: list[dict]) -> None:
    console = Console(highlight=False, markup=False)
    if not records:
        console.print("No matching books.")
        return
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold",
        expand=True,
        pad_edge=False,
        collapse_padding=True,
    )
    table.add_column("Title", ratio=3, min_width=6, overflow="fold")
    table.add_column("Format", min_width=7, overflow="fold")
    table.add_column("Source", min_width=8, max_width=24, overflow="fold")
    table.add_column("Acquired", min_width=10, overflow="fold")
    for record in records:
        table.add_row(
            Text(record["book"]["title"]),
            Text(FORMATS[record["book"]["format"]]),
            Text(record["source"]["name"] if record["source"] else "Unknown"),
            Text(record["acquired_on"] or "Unknown"),
        )
    console.print(table)
    console.print(f"{len(records)} record{'s' if len(records) != 1 else ''}")


def print_record(record: dict) -> None:
    console = Console(highlight=False, markup=False)
    book = record["book"]
    console.print(Text(book["title"], style="bold"))
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column(overflow="fold")
    fields = [
        ("Authors", ", ".join(book["authors"]) or "Unknown"),
        ("Format", FORMATS[book["format"]]),
        ("Source", record["source"]["name"] if record["source"] else "Unknown"),
        (
            "Purchased on" if record["acquisition_kind"] == "purchase" else "Acquired on",
            record["acquired_on"] or "Unknown",
        ),
        ("Quantity", str(record["quantity"])),
        (
            "Record type",
            "Purchase" if record["acquisition_kind"] == "purchase" else "Ownership assertion",
        ),
        ("Order status", ORDER_STATES[record["order_state"]]),
        ("Possession", POSSESSION[record["possession_state"]]),
    ]
    for label, key in (
        ("Edition", "edition"),
        ("Volume", "volume"),
        ("Language", "language"),
        ("ISBN", "isbn"),
    ):
        if book[key] is not None:
            fields.append((label, book[key]))
    if book["file_formats"]:
        fields.append(
            (
                "File formats",
                ", ".join(
                    "Other" if value == "other" else value.upper() for value in book["file_formats"]
                ),
            )
        )
    if book["reference_url"] is not None:
        fields.append(("Product URL", book["reference_url"]))
    fields.append(("Record ID", record["id"]))
    for label, value in fields:
        table.add_row(Text(label), Text(value))
    console.print(table)
