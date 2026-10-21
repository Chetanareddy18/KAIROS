"""Google Sheets connector via gspread + service account JSON."""
import logging
import os

import pandas as pd

from backend.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger("kairos.connector.sheets")


class SheetsConnector(BaseConnector):
    type        = "sheets"
    label       = "Google Sheets"
    description = "Reads a worksheet with a service account (read-only scope)."
    CONFIG_FIELDS = [
        {"name": "spreadsheet_key", "label": "Spreadsheet key", "type": "text", "required": True,
         "help": "the long id in the sheet URL"},
        {"name": "worksheet", "label": "Worksheet", "type": "text", "required": False, "default": "Sheet1"},
        {"name": "credentials_file", "label": "Service account JSON path", "type": "text", "required": False},
    ]

    def __init__(self, source_name: str, config: dict | None = None, spreadsheet_key: str | None = None,
                 worksheet_name: str | None = None, credentials_file: str | None = None, **legacy):
        config = dict(config or {})
        if spreadsheet_key:
            config["spreadsheet_key"] = spreadsheet_key
        if worksheet_name:
            config["worksheet"] = worksheet_name
        if credentials_file:
            config["credentials_file"] = credentials_file
        config.update({k: v for k, v in legacy.items() if v is not None})
        super().__init__(source_name, config)

    def fetch_raw(self, state: dict):
        import gspread
        from google.oauth2.service_account import Credentials

        key = self.config.get("spreadsheet_key")
        if not key:
            raise ConnectorError("'spreadsheet_key' is required")
        creds_file = self.config.get("credentials_file") or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json"
        )
        creds = Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        ws = gspread.authorize(creds).open_by_key(key).worksheet(self.config.get("worksheet", "Sheet1"))
        df = pd.DataFrame(ws.get_all_records())
        return df, state, {"bytes": int(df.memory_usage(deep=True).sum()) if not df.empty else 0}
