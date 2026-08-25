"""Agent 5: Messenger — Telegram Bot API + Gmail SMTP multi-channel delivery."""
import logging
import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("kairos.agent5")

_TG_MAX = 4096


class MessengerAgent:
    def __init__(self):
        self.tg_token    = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.tg_chat_id  = os.getenv("TELEGRAM_CHAT_ID", "")
        self.gmail_user  = os.getenv("GMAIL_USER", "")
        self.gmail_pass  = os.getenv("GMAIL_APP_PASSWORD", "")
        self.alert_email = os.getenv("ALERT_EMAIL", "")
        self._history: list[dict] = []

    def send(self, report: str) -> bool:
        tg_ok    = self._telegram(report)
        email_ok = self._email(report) if self.gmail_user and self.alert_email else True
        self._history.append({"report": report[:200], "telegram": tg_ok, "email": email_ok})
        return tg_ok or email_ok

    def _telegram(self, text: str) -> bool:
        if not self.tg_token or not self.tg_chat_id:
            logger.warning("Telegram not configured")
            return False
        try:
            import httpx
            url    = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            chunks = [text[i:i + _TG_MAX] for i in range(0, len(text), _TG_MAX)]
            for chunk in chunks:
                r = httpx.post(url, json={"chat_id": self.tg_chat_id, "text": chunk}, timeout=10)
                r.raise_for_status()
            logger.info("Telegram alert sent (%d chunk(s))", len(chunks))
            return True
        except Exception as e:
            logger.error("Telegram failed: %s", e)
            return False

    def _email(self, text: str) -> bool:
        try:
            msg            = MIMEText(text)
            msg["Subject"] = "KAIROS Business Alert"
            msg["From"]    = self.gmail_user
            msg["To"]      = self.alert_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(self.gmail_user, self.gmail_pass)
                s.send_message(msg)
            logger.info("Email alert sent to %s", self.alert_email)
            return True
        except Exception as e:
            logger.error("Email failed: %s", e)
            return False

    def get_history(self) -> list[dict]:
        return self._history[-50:]
