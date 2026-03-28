"""알림 서비스 – Telegram Bot 및 SMTP Email 발송."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.text import MIMEText

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Telegram Bot API 및 SMTP 를 통한 알림 전송."""

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def send_telegram(self, message: str) -> bool:
        """Telegram Bot API 로 메시지를 전송합니다.

        Returns:
            True if sent successfully, False otherwise.
        """
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            logger.debug("Telegram not configured, skipping notification")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Telegram notification sent")
                return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    # ── Email (SMTP) ──────────────────────────────────────────────────────────

    def send_email(self, subject: str, body: str, to: str) -> bool:
        """SMTP 로 이메일을 전송합니다 (동기).

        Returns:
            True if sent successfully, False otherwise.
        """
        host = settings.SMTP_HOST
        if not host:
            logger.debug("SMTP not configured, skipping email notification")
            return False

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
        msg["To"] = to

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, settings.SMTP_PORT) as server:
                server.starttls(context=context)
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(msg["From"], [to], msg.as_string())
            logger.info("Email sent to %s: %s", to, subject)
            return True
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return False

    # ── Convenience ───────────────────────────────────────────────────────────

    async def notify(
        self,
        message: str,
        subject: str = "CoinTrader 알림",
        email_to: str | None = None,
    ) -> None:
        """Telegram 과 (선택적) Email 로 동시에 알림을 발송합니다."""
        await self.send_telegram(message)
        if email_to:
            self.send_email(subject, message, email_to)
