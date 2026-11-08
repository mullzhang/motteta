"""Human-readable views of acquisition records."""

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

FORMATS = {"print": "紙", "digital": "電子", "unknown": "不明"}
POSSESSION = {"owned": "所持", "disposed": "手放した", "gift": "贈答用", "unknown": "不明"}
ORDER_STATES = {
    "completed": "完了",
    "ordered": "注文済み",
    "preordered": "予約中",
    "cancelled": "キャンセル",
    "returned": "返品",
    "unknown": "不明",
    None: "対象外",
}


def print_records(records: list[dict]) -> None:
    console = Console(highlight=False, markup=False)
    if not records:
        console.print("該当する本はありません。")
        return
    table = Table(box=box.SIMPLE_HEAD, header_style="bold", expand=True, pad_edge=False)
    table.add_column("書名", ratio=3, min_width=6, overflow="fold")
    table.add_column("形態", min_width=4, overflow="fold")
    table.add_column("購入先", min_width=8, max_width=24, overflow="fold")
    table.add_column("入手日", min_width=10, overflow="fold")
    for record in records:
        table.add_row(
            Text(record["book"]["title"]),
            Text(FORMATS[record["book"]["format"]]),
            Text(record["source"]["name"] if record["source"] else "不明"),
            Text(record["acquired_on"] or "不明"),
        )
    console.print(table)
    console.print(f"{len(records)}件")


def print_record(record: dict) -> None:
    console = Console(highlight=False, markup=False)
    book = record["book"]
    console.print(Text(book["title"], style="bold"))
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column(overflow="fold")
    fields = [
        ("著者", "、".join(book["authors"]) or "不明"),
        ("形態", FORMATS[book["format"]]),
        ("購入先", record["source"]["name"] if record["source"] else "不明"),
        (
            "購入日" if record["acquisition_kind"] == "purchase" else "入手日",
            record["acquired_on"] or "不明",
        ),
        ("数量", f"{record['quantity']}冊"),
        ("記録種別", "購入" if record["acquisition_kind"] == "purchase" else "所持申告"),
        ("注文状態", ORDER_STATES[record["order_state"]]),
        ("所持状態", POSSESSION[record["possession_state"]]),
    ]
    for label, key in (("版", "edition"), ("巻", "volume"), ("言語", "language"), ("ISBN", "isbn")):
        if book[key] is not None:
            fields.append((label, book[key]))
    if book["file_formats"]:
        fields.append(
            (
                "ファイル形式",
                "、".join(
                    "その他" if value == "other" else value.upper()
                    for value in book["file_formats"]
                ),
            )
        )
    if book["reference_url"] is not None:
        fields.append(("商品URL", book["reference_url"]))
    fields.append(("記録ID", record["id"]))
    for label, value in fields:
        table.add_row(Text(label), Text(value))
    console.print(table)
