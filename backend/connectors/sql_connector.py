"""SQL connector — PostgreSQL, MySQL, SQLite via SQLAlchemy."""
import logging

import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger("kairos.connector.sql")


class SQLConnector:
    def __init__(
        self,
        source_name: str,
        connection_url: str,
        query: str,
        metric_col: str = "metric_name",
        value_col:  str = "value",
        ts_col:     str = "timestamp",
    ):
        self.source_name    = source_name
        self.connection_url = connection_url
        self.query          = query
        self.metric_col     = metric_col
        self.value_col      = value_col
        self.ts_col         = ts_col

    def fetch(self) -> pd.DataFrame:
        engine = create_engine(self.connection_url)
        try:
            with engine.connect() as conn:
                df = pd.read_sql(text(self.query), conn)
        finally:
            engine.dispose()
        return df.rename(columns={
            self.metric_col: "metric_name",
            self.value_col:  "value",
            self.ts_col:     "timestamp",
        })
