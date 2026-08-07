# Vertical Passage — Daily Pre-Order Report

Finds orders for a specific client that are **stuck on backorder** but where
inventory is **already on an open Purchase Order (replenishment)** in ShipHero
— and that **don't already have the `preorder` tag**. It:

1. Pulls open orders for the client from ShipHero (GraphQL public API)
2. Pulls open Purchase Orders for that same client/warehouse
3. Matches backordered line items to SKUs that have replenishment inbound
4. Drops any order that's already tagged `preorder` (someone has already
   seen and handled it)
5. Writes the remaining matches to a CSV
6. Emails the CSV to a distribution list via Gmail

This is **read-only against ShipHero** — the automation does not write the
`preorder` tag itself. Tagging an order is what takes it off tomorrow's
report, so however you choose to apply that tag (manually in the ShipHero
UI, a separate process, etc.) doubles as your "handled" signal.

Runs daily on a schedule via **GitHub Actions** — no server to maintain.

---

## How the matching works

ShipHero doesn't have a single "backorder" order status you can filter on.
Instead, each order line item has a `backorder_quantity` field. This tool:

- Fetches orders for the client (`customer_account_id`) that are not yet
  fully fulfilled, over a configurable lookback window
- Keeps only line items where `backorder_quantity > 0`
- Fetches open Purchase Orders for the same client (`fulfillment_status`
  not `closed`)
- For each PO line item, computes `quantity - quantity_received` — if that's
  > 0, that SKU has inbound replenishment
- Any backordered order line item whose SKU appears in that open-PO set,
  **on an order that doesn't already have the `preorder` tag**, is included
  in the report

Because the tag itself is the "already reported" marker, an order naturally
drops off the daily report once it gets tagged — there's no separate
dedup/state tracking needed.

## Repo layout

```
src/
  config.py           # env-driven settings
  shiphero_auth.py     # refresh-token -> access-token exchange
  shiphero_client.py   # GraphQL calls: orders, purchase_orders, tagging
  matcher.py           # backorder <-> open PO matching logic
  csv_export.py        # writes the daily CSV
  gmail_client.py       # sends the email with the CSV attached via Gmail API
  main.py              # orchestrates the whole run
scripts/
  get_gmail_refresh_token.py   # one-time local script to mint a Gmail refresh token
.github/workflows/
  daily-preorder-report.yml    # the daily cron
```

## One-time setup

### 1. ShipHero refresh token

You already have a token from logging in / a third-party developer user.
If not, get one:

```bash
curl -X POST -H "Content-Type: application/json" -d \
  '{"username":"YOUR_EMAIL","password":"YOUR_PASSWORD"}' \
  "https://public-api.shiphero.com/auth/token"
```

Save the `refresh_token` from the response — that's what the script uses.
It does **not** rotate on refresh, so you set it once as a GitHub secret and
you're done (access tokens expire every 28 days, but the script re-derives
a fresh one every run, so you never touch this again unless you revoke it).

Recommended: create a **dedicated third-party developer user** in ShipHero
(Dashboard → Users → "+Add Third-Party Developer") instead of using your own
login, so this automation isn't tied to your personal credentials.

### 2. Find your client's `customer_account_id` and `warehouse_id`

Run this in ShipHero's GraphQL Playground (or ask me and I'll pull it via the
API once your token is set up):

```graphql
query {
  account {
    data {
      is_3pl
      warehouses { id identifier }
      customers(first: 50) {
        edges { node { id username email } }
      }
    }
  }
}
```

Find the customer in that list — its `id` is the `customer_account_id`.

### 3. Gmail API OAuth (one-time, run locally — not in GitHub Actions)

1. In Google Cloud Console, create a project, enable the **Gmail API**, and
   create an **OAuth Client ID** of type "Desktop app". Download the
   `client_secret.json`.
2. Locally:
   ```bash
   pip install google-auth-oauthlib
   python scripts/get_gmail_refresh_token.py --client-secret client_secret.json
   ```
3. This opens a browser, you approve access to send mail as yourself, and it
   prints a `refresh_token`. That token, plus the client ID/secret, are what
   go into GitHub Secrets. This only needs to be done once.

### 4. GitHub repo secrets

Add these under Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `SHIPHERO_REFRESH_TOKEN` | from step 1 |
| `SHIPHERO_CUSTOMER_ACCOUNT_ID` | from step 2 |
| `SHIPHERO_WAREHOUSE_ID` | from step 2 |
| `GMAIL_CLIENT_ID` | from step 3 |
| `GMAIL_CLIENT_SECRET` | from step 3 |
| `GMAIL_REFRESH_TOKEN` | from step 3 |
| `GMAIL_SENDER_EMAIL` | the Gmail address sending the report |
| `REPORT_RECIPIENTS` | comma-separated list, e.g. `imran@verticalpassage.com,ops@verticalpassage.com` |

### 5. Adjust the schedule

Edit `.github/workflows/daily-preorder-report.yml` — the `cron` line is in
UTC. It's currently set to 11:00 UTC (7:00am ET / 6:00am during EDT — adjust
for daylight saving as needed, GitHub Actions cron doesn't auto-shift).

## Running locally (for testing before you rely on the schedule)

```bash
cd preorder-report
pip install -r requirements.txt
export SHIPHERO_REFRESH_TOKEN=...
export SHIPHERO_CUSTOMER_ACCOUNT_ID=...
export SHIPHERO_WAREHOUSE_ID=...
export GMAIL_CLIENT_ID=...
export GMAIL_CLIENT_SECRET=...
export GMAIL_REFRESH_TOKEN=...
export GMAIL_SENDER_EMAIL=...
export REPORT_RECIPIENTS=you@verticalpassage.com
python src/main.py --dry-run   # writes the CSV and prints what it would email, but doesn't send anything
python src/main.py             # full run: writes CSV + sends email
```

## Things worth double-checking before first real run

- **Confirm the enum/field names still match your ShipHero schema version.**
  I pulled these from ShipHero's live public docs, but GraphQL Playground
  against your own account (Schema tab) is the source of truth if anything
  errors out.
- **Quota/throttling**: ShipHero rate-limits by query complexity. The client
  paginates with `first: 50` and 
  will back off automatically if it hits a throttling error, using the
  `time_remaining` value ShipHero returns.
- **Lookback window**: defaults to 30 days of orders (`LOOKBACK_DAYS` in
  `config.py`) — tune this to your order volume.
