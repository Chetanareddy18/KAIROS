"""Backwards-compatible alias: CSVConnector is the general FileConnector."""
from backend.connectors.file_connector import FileConnector


class CSVConnector(FileConnector):
    type = "csv"
    label = "CSV / Excel file"
