"""Test configuration: isolated temp data dir, no network side effects (no Telegram/Groq/LLM)."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="kairos_test_"))
os.environ.update({
    "KAIROS_ENV": "test",
    "KAIROS_DATA_DIR": str(_TMP / "data"),
    "KAIROS_DB_PATH": str(_TMP / "kairos_test.duckdb"),
    "KAIROS_SOURCES_FILE": str(_TMP / "no_sources.yaml"),
    "KAIROS_SCHEDULER_ENABLED": "false",
    "KAIROS_USE_PROPHET": "false",
    "KAIROS_LLM_ENABLED": "false",
    "KAIROS_API_KEY": "",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "GMAIL_USER": "",
    "GROQ_API_KEY": "",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.db import Database  # noqa: E402


@pytest.fixture
def tmp_dir(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(str(tmp_path / "test.duckdb"))
    yield database
    database.close()
