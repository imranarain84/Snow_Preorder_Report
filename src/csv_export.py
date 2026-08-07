"""Writes matched pre-order rows to a CSV file."""
import csv
from pathlib import Path

FIELDNAMES = [
    "order_number",
    "order_date",
    "customer_email",
    "sku",
    "product_name",
    "qty_backordered",
    "po_number",
    "po_date",
    "qty_inbound_on_po",
    "order_id",
    "po_id",
]


def write_csv(rows: list[dict], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path
