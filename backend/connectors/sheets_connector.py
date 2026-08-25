"""Google Sheets connector via gspread + service account JSON."""
import logging
import os

import pandas as pd

logger = logging.getLogger("kairos.connector.sheets")


class SheetsConnector:
    def __init__(
        self,
        source_name: str,
        spreadsheet_key: str,
        worksheet_name: str  = "Sheet1",
        metric_col: str      = "metric_name",
        value_col:  str      = "value",
        ts_col:     str      = "timestamp",
        credentials_file: str | None = None,
    ):
        self.source_name     = source_name
        self.spreadsheet_key = spreadsheet_key
        self.worksheet_name  = worksheet_name
        self.metric_col      = metric_col
        self.value_col       = value_col
        self.ts_col          = ts_col
        self.credentials_file = credentials_file or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json"
        )

    def fetch(self) -> pd.DataFrame:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds  = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
        gc     = gspread.authorize(creds)
        ws     = gc.open_by_key(self.spreadsheet_key).worksheet(self.worksheet_name)
        df     = pd.DataFrame(ws.get_all_records())
        return df.rename(columns={
            self.metric_col: "metric_name",
            self.value_col:  "value",
            self.ts_col:     "timestamp",
        })
