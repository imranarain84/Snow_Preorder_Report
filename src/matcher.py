"""Matches backordered order line items against SKUs with inbound replenishment."""
from typing import Any


def find_preorder_matches(
    backordered_orders: list[dict],
    open_po_skus: dict[str, list[dict]],
    preorder_tag: str,
) -> list[dict]:
    """Returns one row per (order, matched line item, matching PO) so the CSV
    can show exactly which PO is covering which backordered item.

    Orders that already carry `preorder_tag` are skipped — the tag is what
    marks an order as "already surfaced/handled", so once it's tagged
    (manually, by someone reading a prior day's report) it drops off this
    report on its own.
    """
    rows: list[dict] = []
    for order in backordered_orders:
        if preorder_tag in (order.get("tags") or []):
            continue
        for line_item in order["backordered_line_items"]:
            sku = line_item["sku"]
            matching_pos = open_po_skus.get(sku)
            if not matching_pos:
                continue
            for po in matching_pos:
                rows.append(
                    {
                        "order_id": order["id"],
                        "order_number": order["order_number"],
                        "order_date": order.get("order_date"),
                        "customer_email": order.get("email"),
                        "sku": sku,
                        "product_name": line_item.get("product_name"),
                        "qty_backordered": line_item.get("backorder_quantity"),
                        "po_number": po["po_number"],
                        "po_id": po["po_id"],
                        "po_date": po.get("po_date"),
                        "qty_inbound_on_po": po["qty_inbound"],
                    }
                )
    return rows
