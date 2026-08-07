"""Environment-driven configuration. No secrets live in code."""
import os


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in your shell (local run) or as a GitHub Actions secret."
        )
    return value


class Config:
    def __init__(self):
        self.shiphero_refresh_token = _require("SHIPHERO_REFRESH_TOKEN")
        self.customer_account_id = _require("SHIPHERO_CUSTOMER_ACCOUNT_ID")
        self.warehouse_id = _require("SHIPHERO_WAREHOUSE_ID")

        self.gmail_client_id = _require("GMAIL_CLIENT_ID")
        self.gmail_client_secret = _require("GMAIL_CLIENT_SECRET")
        self.gmail_refresh_token = _require("GMAIL_REFRESH_TOKEN")
        self.gmail_sender_email = _require("GMAIL_SENDER_EMAIL")

        recipients_raw = _require("REPORT_RECIPIENTS")
        self.recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

        self.lookback_days = int(os.environ.get("LOOKBACK_DAYS", "30"))
        self.preorder_tag = os.environ.get("PREORDER_TAG", "preorder")

        self.shiphero_auth_url = "https://public-api.shiphero.com/auth/refresh"
        self.shiphero_graphql_url = "https://public-api.shiphero.com/graphql"
