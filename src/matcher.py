"""Finds backordered line items whose SKU has NO open replenishment PO at
all — these are stockouts we haven't even ordered more inventory for.

SKUs affecting 5+ distinct orders are excluded on purpose: at that volume
it's presumably already a known, actively-managed issue. This report exists
to surface the smaller, easy-to-miss ones.
"""


def find_no_po_matches(
    backordered_orders: list[dict],
    open_po_skus: dict[str, list[dict]],
    preorder_tag: str,
    max_orders_per_sku: int = 5,
) -> list[dict]:
    """Returns one row per backordered line item whose SKU has no inbound
    PO, but only for SKUs affecting fewer than `max_orders_per_sku` distinct
    orders.

    Orders already carrying `preorder_tag` are skipped, same as before —
    the tag marks an order as already reviewed/handled.
    """
    candidates_by_sku: dict[str, list[dict]] = {}

    for order in backordered_orders:
        if preorder_tag in (order.get("tags") or []):
            continue
        for line_item in order["backordered_line_items"]:
            sku = line_item["sku"]
            if sku in open_po_skus:
                continue  # has replenishment inbound — not what we want here
            candidates_by_sku.setdefault(sku, []).append(
                {
                    "order_id": order["id"],
                    "order_number": order["order_number"],
                    "order_date": order.get("order_date"),
                    "customer_email": order.get("email"),
                    "sku": sku,
                    "product_name": line_item.get("product_name"),
                    "qty_backordered": line_item.get("backorder_quantity"),
                }
            )

    rows: list[dict] = []
    for sku, items in candidates_by_sku.items():
        distinct_orders = {item["order_id"] for item in items}
        if len(distinct_orders) >= max_orders_per_sku:
            continue  # too many affected orders — treat as already known/handled
        for item in items:
            item["orders_affected_for_sku"] = len(distinct_orders)
            rows.append(item)

    return rows
