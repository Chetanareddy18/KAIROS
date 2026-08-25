"""CSV / Excel connector — local or remote flat files."""
import logging

import pandas as pd

logger = logging.getLogger("kairos.connector.csv")


class CSVConnector:
    def __init__(
        self,
        source_name: str,
        file_path: str,
        metric_col: str = "metric_name",
        value_col:  str = "value",
        ts_col:     str = "timestamp",
    ):
        self.source_name = source_name
        self.file_path   = file_path
        self.metric_col  = metric_col
        self.value_col   = value_col
        self.ts_col      = ts_col

    def fetch(self) -> pd.DataFrame:
        path = self.file_path.lower()
        df   = pd.read_excel(self.file_path) if path.endswith((".xlsx", ".xls")) else pd.read_csv(self.file_path)
        return df.rename(columns={
            self.metric_col: "metric_name",
            self.value_col:  "value",
            self.ts_col:     "timestamp",
        })
