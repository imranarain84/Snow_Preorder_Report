"""Thin GraphQL client for the ShipHero public API.

Field names below are taken from ShipHero's published docs/examples
(developer.shiphero.com) as of Aug 2026. If ShipHero changes their schema,
GraphQL Playground against your own account (Docs/Schema tab) is the source
of truth — this file is the one place to update field names if so.
"""
import re
import time
from typing import Any, Optional

import requests


class ShipHeroClient:
    def __init__(self, access_token: str, graphql_url: str):
        self.graphql_url = graphql_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )

    def _post(self, query: str, variables: Optional[dict] = None) -> dict:
        """POST a GraphQL query, retrying once if throttled."""
        for attempt in range(2):
            resp = self.session.post(
                self.graphql_url,
                json={"query": query, "variables": variables or {}},
                timeout=60,
            )
            body = resp.json()

            errors = body.get("errors")
            if errors:
                throttle_error = next(
                    (e for e in errors if e.get("code") == 30), None
                )
                if throttle_error and attempt == 0:
                    wait_seconds = self._parse_wait_seconds(
                        throttle_error.get("time_remaining", "5 seconds")
                    )
                    time.sleep(min(wait_seconds, 90) + 1)
                    continue
                raise RuntimeError(f"ShipHero GraphQL error: {errors}")

            return body["data"]

        raise RuntimeError("ShipHero GraphQL request failed after retry")

    @staticmethod
    def _parse_wait_seconds(time_remaining: str) -> int:
        match = re.search(r"(\d+)", time_remaining)
        return int(match.group(1)) if match else 5

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_backordered_orders(
        self, customer_account_id: Optional[str], warehouse_id: Optional[str], order_date_from: str
    ) -> list[dict]:
        """Returns orders for the client with at least one line item that has
        backorder_quantity > 0. Filters client-side since ShipHero doesn't
        expose a single 'backorder' fulfillment_status to filter on.
        """
        query = """
        query BackorderedOrders($customer_account_id: String, $warehouse_id: String,
                                 $order_date_from: ISODateTime, $after: String) {
          orders(customer_account_id: $customer_account_id,
                 warehouse_id: $warehouse_id,
                 order_date_from: $order_date_from,
                 fulfillment_status: "pending") {
            request_id
            complexity
            data(first: 50, after: $after) {
              pageInfo { hasNextPage endCursor }
              edges {
                node {
                  id
                  legacy_id
                  order_number
                  fulfillment_status
                  order_date
                  account_id
                  email
                  tags
                  line_items(first: 50) {
                    edges {
                      node {
                        id
                        sku
                        product_name
                        quantity
                        quantity_allocated
                        backorder_quantity
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        orders = []
        after = None
        while True:
            data = self._post(
                query,
                {
                    "customer_account_id": customer_account_id,
                    "warehouse_id": warehouse_id,
                    "order_date_from": order_date_from,
                    "after": after,
                },
            )
            page = data["orders"]["data"]
            for edge in page["edges"]:
                node = edge["node"]
                backordered_items = [
                    li["node"]
                    for li in node["line_items"]["edges"]
                    if li["node"].get("backorder_quantity", 0) > 0
                ]
                if backordered_items:
                    node["backordered_line_items"] = backordered_items
                    orders.append(node)
            if page["pageInfo"]["hasNextPage"]:
                after = page["pageInfo"]["endCursor"]
            else:
                break
        return orders

    # ------------------------------------------------------------------
    # Purchase Orders
    # ------------------------------------------------------------------

    def get_open_purchase_order_skus(
        self, customer_account_id: Optional[str], warehouse_id: Optional[str]
    ) -> dict[str, list[dict]]:
        """Returns a dict of sku -> list of {po_number, po_id, qty_inbound,
        expected_date} for every open PO line item still awaiting receipt
        (quantity > quantity_received).
        """
        query = """
        query OpenPOs($customer_account_id: String, $warehouse_id: String, $after: String) {
          purchase_orders(customer_account_id: $customer_account_id,
                           warehouse_id: $warehouse_id) {
            request_id
            complexity
            data(first: 50, after: $after) {
              pageInfo { hasNextPage endCursor }
              edges {
                node {
                  id
                  po_number
                  fulfillment_status
                  po_date
                  line_items(first: 100) {
                    edges {
                      node {
                        sku
                        quantity
                        quantity_received
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        sku_map: dict[str, list[dict]] = {}
        after = None
        while True:
            data = self._post(
                query,
                {
                    "customer_account_id": customer_account_id,
                    "warehouse_id": warehouse_id,
                    "after": after,
                },
            )
            page = data["purchase_orders"]["data"]
            for edge in page["edges"]:
                po = edge["node"]
                if po.get("fulfillment_status") == "closed":
                    continue
                for li_edge in po["line_items"]["edges"]:
                    li = li_edge["node"]
                    qty_inbound = (li.get("quantity") or 0) - (
                        li.get("quantity_received") or 0
                    )
                    if qty_inbound > 0:
                        sku_map.setdefault(li["sku"], []).append(
                            {
                                "po_id": po["id"],
                                "po_number": po["po_number"],
                                "po_date": po.get("po_date"),
                                "qty_inbound": qty_inbound,
                            }
                        )
            if page["pageInfo"]["hasNextPage"]:
                after = page["pageInfo"]["endCursor"]
            else:
                break
        return sku_map
