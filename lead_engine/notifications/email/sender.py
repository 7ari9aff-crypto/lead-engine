"""SMTP email sender for Lead Engine notifications.

Thin wrapper around ``smtplib`` + ``email.message.EmailMessage``. The goal
is a single, predictable call site for outbound notifications:
``EmailSender.send(...)`` returns a small dict and never raises on SMTP
problems — call sites (job manager, approval flow, lead-batch handoff)
should be able to fire-and-log without try/except noise.
"""
from __future__ import annotations

import smtplib
import uuid
from email.message import EmailMessage


class EmailSender:
    """Send a single multipart/alternative message over SMTP.

    Default behavior is opportunistic TLS on port 587 (the modern norm).
    Set ``use_tls=False`` to connect with implicit TLS via ``SMTP_SSL``
    (useful for port 465 relays).
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        default_from: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.default_from = default_from

    def send(
        self,
        to: str | list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
        from_addr: str | None = None,
    ) -> dict:
        """Build and dispatch the email.

        Returns ``{"ok": True, "message_id": "<uuid4 hex>"}`` on success and
        ``{"ok": False, "error": "<message>"}`` on any SMTP/OS error. Never
        raises so call sites stay simple.
        """
        recipients = [to] if isinstance(to, str) else list(to)
        sender = from_addr or self.default_from

        msg = EmailMessage()
        if sender:
            msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        # Plain-text part first (per RFC 2046 preferred ordering for clients
        # that only understand text). HTML alternative added second.
        msg.set_content(text_body or "")
        msg.add_alternative(html_body, subtype="html")

        message_id = uuid.uuid4().hex
        try:
            client = (
                smtplib.SMTP_SSL(self.host, self.port, timeout=30)
                if not self.use_tls
                else smtplib.SMTP(self.host, self.port, timeout=30)
            )
            with client as smtp:
                smtp.ehlo()
                if self.use_tls and self.username and self.password:
                    smtp.starttls(context=None)
                    smtp.ehlo()
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
        except smtplib.SMTPException as exc:
            return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
        except OSError as exc:
            return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}

        return {"ok": True, "message_id": message_id}
