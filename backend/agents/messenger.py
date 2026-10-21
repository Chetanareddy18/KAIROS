"""Agent 5: Messenger — Telegram Bot API + Gmail SMTP, with persisted delivery history."""
import logging
import os
import smtplib
from email.mime.text import MIMEText

import httpx

from backend.db import Database, get_db

logger = logging.getLogger("kairos.agent5")

_TG_MAX = 4096


class MessengerAgent:
    def __init__(self, db: Database | None = None):
        self.db          = db or get_db()
        self.tg_token    = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.tg_chat_id  = os.getenv("TELEGRAM_CHAT_ID", "")
        self.gmail_user  = os.getenv("GMAIL_USER", "")
        self.gmail_pass  = os.getenv("GMAIL_APP_PASSWORD", "")
        self.alert_email = os.getenv("ALERT_EMAIL", "")

    @property
    def channels(self) -> dict:
        return {
            "telegram": bool(self.tg_token and self.tg_chat_id),
            "email": bool(self.gmail_user and self.gmail_pass and self.alert_email),
        }

    def send(self, report: str, anomaly_count: int = 0, verified: bool | None = None,
             model: str | None = None, subject: str = "KAIROS Business Alert") -> bool:
        tg_ok    = self._telegram(f"🔔 {subject}\n\n{report}") if self.channels["telegram"] else False
        email_ok = self._email(report, subject) if self.channels["email"] else False
        self.db.execute(
            "INSERT INTO alerts (report, telegram, email, anomaly_count, verified, model) VALUES (?, ?, ?, ?, ?, ?)",
            [report, tg_ok, email_ok, anomaly_count, verified, model],
        )
        if not (tg_ok or email_ok):
            logger.warning("Alert stored, but no delivery channel succeeded (configured: %s)", self.channels)
        return tg_ok or email_ok

    def _telegram(self, text: str) -> bool:
        try:
            url    = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            chunks = [text[i:i + _TG_MAX] for i in range(0, len(text), _TG_MAX)]
            for chunk in chunks:
                r = httpx.post(url, json={"chat_id": self.tg_chat_id, "text": chunk}, timeout=10)
                r.raise_for_status()
            logger.info("Telegram alert sent (%d chunk(s))", len(chunks))
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Telegram failed: %s", str(e).replace(self.tg_token, "***"))
            return False

    def _email(self, text: str, subject: str) -> bool:
        try:
            msg            = MIMEText(text)
            msg["Subject"] = subject
            msg["From"]    = self.gmail_user
            msg["To"]      = self.alert_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
                s.login(self.gmail_user, self.gmail_pass)
                s.send_message(msg)
            logger.info("Email alert sent to %s", self.alert_email)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Email failed: %s", e)
            return False

    def get_history(self, limit: int = 50) -> list[dict]:
        df = self.db.df(
            "SELECT id, sent_at, report, telegram, email, anomaly_count, verified, model "
            "FROM alerts ORDER BY sent_at DESC LIMIT ?", [limit],
        )
        if not df.empty:
            df["sent_at"] = df["sent_at"].map(lambda t: t.isoformat())
        return df.astype(object).where(df.notna(), None).to_dict(orient="records")
