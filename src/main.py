"""Daily pre-order report: finds backordered orders covered by an open PO,
writes a CSV, tags the orders in ShipHero, and emails the CSV out.

Usage:
    python src/main.py             # full run
    python src/main.py --dry-run   # writes CSV, prints what it WOULD tag/email
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from config import Config
from shiphero_auth import get_access_token
from shiphero_client import ShipHeroClient
from matcher import find_preorder_matches
from csv_export import write_csv
from gmail_client import send_report_email


def run(dry_run: bool = False) -> None:
    cfg = Config()

    print("Authenticating with ShipHero...")
    access_token = get_access_token(cfg.shiphero_refresh_token, cfg.shiphero_auth_url)
    client = ShipHeroClient(access_token, cfg.shiphero_graphql_url)

    order_date_from = (
        datetime.utcnow() - timedelta(days=cfg.lookback_days)
    ).strftime("%Y-%m-%d")

    print(f"Fetching backordered orders since {order_date_from}...")
    backordered_orders = client.get_backordered_orders(
        cfg.customer_account_id, cfg.warehouse_id, order_date_from
    )
    print(f"  found {len(backordered_orders)} orders with backordered line items")

    print("Fetching open purchase orders...")
    open_po_skus = client.get_open_purchase_order_skus(
        cfg.customer_account_id, cfg.warehouse_id
    )
    print(f"  found {len(open_po_skus)} SKUs with inbound replenishment")

    rows = find_preorder_matches(backordered_orders, open_po_skus, cfg.preorder_tag)
    print(f"Matched {len(rows)} backordered line item(s) to open POs "
          f"(excluding orders already tagged '{cfg.preorder_tag}')")

    if not rows:
        print("No new pre-order matches today — nothing to email.")
        return

    today = datetime.utcnow().strftime("%Y-%m-%d")
    csv_path = Path(f"output/preorder_report_{today}.csv")
    write_csv(rows, csv_path)
    print(f"Wrote CSV to {csv_path}")

    order_numbers = sorted({row["order_number"] for row in rows})

    if dry_run:
        print(f"[dry-run] Would email CSV to: {cfg.recipients}")
        print(f"[dry-run] Orders in report: {order_numbers}")
        return

    print(f"Emailing report to {cfg.recipients}...")
    body = (
        f"Daily pre-order report — {today}\n\n"
        f"{len(order_numbers)} order(s) / {len(rows)} line item(s) are on backorder "
        f"and covered by an open replenishment PO, but are not yet tagged "
        f"'{cfg.preorder_tag}' in ShipHero.\n\n"
        f"Orders: {', '.join(order_numbers)}\n\n"
        f"Full detail attached as CSV."
    )
    send_report_email(
        client_id=cfg.gmail_client_id,
        client_secret=cfg.gmail_client_secret,
        refresh_token=cfg.gmail_refresh_token,
        sender=cfg.gmail_sender_email,
        recipients=cfg.recipients,
        subject=f"Pre-Order Report — {today}",
        body_text=body,
        csv_path=csv_path,
    )
    print("Email sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
