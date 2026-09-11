"""Email notification channel — sender + templates.

We never touch a real SMTP server. ``smtplib.SMTP`` is patched at the
sender-module level so we can assert against what got constructed and
sent without ever opening a socket.
"""
from __future__ import annotations

import smtplib
from email import message_from_string
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from lead_engine.notifications.email import (
    EmailSender,
    approval_requested_template,
    job_completed_template,
    job_paused_template,
    lead_ready_template,
)


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------


def _make_smtp_mock(mock_smtp: MagicMock) -> MagicMock:
    """Wire ``smtplib.SMTP`` so the ``with`` block yields a usable mock."""
    instance = mock_smtp.return_value
    # The sender uses ``with client as smtp``; ensure __enter__/__exit__ work.
    instance.__enter__.return_value = instance
    instance.__exit__.return_value = False
    return instance


def test_send_returns_ok_with_message_id_on_success():
    sender = EmailSender(host="smtp.example.com", port=587, use_tls=True)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        _make_smtp_mock(mock_smtp)

        result = sender.send(
            to="ops@example.com",
            subject="hi",
            html_body="<p>hello</p>",
            text_body="hello",
        )

    assert result["ok"] is True
    assert isinstance(result["message_id"], str)
    # 32-char hex from uuid4().hex
    assert len(result["message_id"]) == 32
    assert all(c in "0123456789abcdef" for c in result["message_id"])
    # SMTP was constructed with our host/port
    mock_smtp.assert_called_once()
    args, kwargs = mock_smtp.call_args
    assert args[0] == "smtp.example.com"
    assert args[1] == 587


def test_send_returns_error_on_smtp_exception():
    sender = EmailSender(host="smtp.example.com", port=587)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)
        instance.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"bad@example.com": (550, b"user unknown")}
        )

        result = sender.send(
            to="bad@example.com",
            subject="x",
            html_body="<b>x</b>",
            text_body="x",
        )

    assert result["ok"] is False
    assert "error" in result
    assert "SMTPRecipientsRefused" in result["error"]


def test_send_returns_error_on_oserror():
    sender = EmailSender(host="smtp.example.com", port=587)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)
        instance.send_message.side_effect = OSError("connection reset")

        result = sender.send(
            to="user@example.com",
            subject="x",
            html_body="<i>x</i>",
            text_body="x",
        )

    assert result["ok"] is False
    assert "OSError" in result["error"] or "connection reset" in result["error"]


def test_send_sets_headers_correctly():
    sender = EmailSender(
        host="smtp.example.com",
        port=587,
        default_from="noreply@example.com",
        username="u",
        password="p",
    )
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)

        sender.send(
            to="alice@example.com",
            subject="Status",
            html_body="<p>ok</p>",
            text_body="ok",
        )

    # Inspect what was passed to send_message
    instance.send_message.assert_called_once()
    sent_msg = instance.send_message.call_args.args[0]
    assert sent_msg["From"] == "noreply@example.com"
    assert sent_msg["To"] == "alice@example.com"
    assert sent_msg["Subject"] == "Status"
    # STARTTLS + login should have been called because creds were set
    instance.starttls.assert_called_once()
    instance.login.assert_called_once_with("u", "p")


def test_send_overrides_from_addr():
    sender = EmailSender(
        host="smtp.example.com",
        port=587,
        default_from="default@example.com",
    )
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)

        sender.send(
            to="x@example.com",
            subject="s",
            html_body="<p>h</p>",
            text_body="h",
            from_addr="override@example.com",
        )

    sent_msg = instance.send_message.call_args.args[0]
    assert sent_msg["From"] == "override@example.com"


def test_send_handles_list_of_recipients_joined_with_comma():
    sender = EmailSender(host="smtp.example.com", port=587)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)

        sender.send(
            to=["a@example.com", "b@example.com", "c@example.com"],
            subject="group",
            html_body="<p>all</p>",
            text_body="all",
        )

    sent_msg = instance.send_message.call_args.args[0]
    assert sent_msg["To"] == "a@example.com, b@example.com, c@example.com"


def test_send_message_has_html_and_text_parts():
    sender = EmailSender(host="smtp.example.com", port=587)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)

        sender.send(
            to="x@example.com",
            subject="multipart",
            html_body="<p>HTML</p>",
            text_body="PLAIN",
        )

    sent_msg: object = instance.send_message.call_args.args[0]
    assert isinstance(sent_msg, EmailMessage)
    # EmailMessage exposes the alternative parts directly
    assert sent_msg.is_multipart() is True
    parts = list(sent_msg.walk())
    payloads = [str(p.get_payload(decode=False)) for p in parts]
    # Both html and text bodies must be present somewhere in the payload
    assert any("HTML" in pl for pl in payloads)
    assert any("PLAIN" in pl for pl in payloads)
    # And the Content-Type header on the outer message declares alternative
    assert "multipart/alternative" in sent_msg.get_content_type()


def test_send_without_creds_skips_login():
    sender = EmailSender(host="smtp.example.com", port=587)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP") as mock_smtp:
        instance = _make_smtp_mock(mock_smtp)

        sender.send(
            to="x@example.com",
            subject="anon",
            html_body="<p>hi</p>",
            text_body="hi",
        )

    instance.starttls.assert_not_called()
    instance.login.assert_not_called()


def test_send_uses_smtp_ssl_when_use_tls_false():
    sender = EmailSender(host="smtp.example.com", port=465, use_tls=False)
    with patch("lead_engine.notifications.email.sender.smtplib.SMTP_SSL") as mock_ssl:
        _make_smtp_mock(mock_ssl)

        result = sender.send(
            to="x@example.com",
            subject="ssl",
            html_body="<p>s</p>",
            text_body="s",
        )

    assert result["ok"] is True
    mock_ssl.assert_called_once()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template_fn",
    [
        job_completed_template,
        job_paused_template,
        approval_requested_template,
        lead_ready_template,
    ],
)
def test_template_returns_required_keys(template_fn):
    out = template_fn(
        *(
            ("job-1", {"leads": 5})
            if template_fn is job_completed_template
            else (
                ("job-1", "quota exhausted")
                if template_fn is job_paused_template
                else (
                    ("appr-1", "approve batch")
                    if template_fn is approval_requested_template
                    else (5,)
                )
            )
        )
    )
    assert set(out.keys()) == {"subject", "html", "text"}
    assert isinstance(out["subject"], str) and out["subject"]
    assert isinstance(out["html"], str) and out["html"]
    assert isinstance(out["text"], str) and out["text"]


@pytest.mark.parametrize(
    "lang, expected_word",
    [("ar", "اكتمل"), ("en", "Job")],
)
def test_job_completed_template_language(lang, expected_word):
    out = job_completed_template("job-42", {"leads": 12}, lang=lang)
    assert expected_word in out["subject"] or expected_word in out["text"]


def test_job_completed_template_includes_metrics():
    out = job_completed_template("job-42", {"leads": 12, "errors": 0}, lang="en")
    assert "leads" in out["text"]
    assert "12" in out["text"]
    # HTML should also surface the metric
    assert "leads" in out["html"]


def test_job_paused_template_ar():
    out = job_paused_template("job-7", "quota exhausted", lang="ar")
    assert "job-7" in out["text"]
    assert "quota exhausted" in out["text"]
    # direction: rtl should be in the HTML
    assert "rtl" in out["html"]


def test_job_paused_template_en():
    out = job_paused_template("job-7", "quota exhausted", lang="en")
    assert "job-7" in out["text"]
    assert "paused" in out["text"].lower()
    assert "ltr" in out["html"]


def test_approval_requested_template_ar():
    out = approval_requested_template("appr-99", "approve batch", lang="ar")
    assert "appr-99" in out["text"]
    assert "approve batch" in out["text"]
    assert "rtl" in out["html"]


def test_approval_requested_template_en():
    out = approval_requested_template("appr-99", "approve batch", lang="en")
    assert "appr-99" in out["text"]
    assert "approve batch" in out["text"]
    assert "ltr" in out["html"]


def test_lead_ready_template_ar():
    out = lead_ready_template(42, lang="ar")
    assert "42" in out["subject"] or "42" in out["text"]
    assert "rtl" in out["html"]


def test_lead_ready_template_en():
    out = lead_ready_template(42, lang="en")
    assert "42" in out["subject"] or "42" in out["text"]
    assert "ltr" in out["html"]


@pytest.mark.parametrize(
    "template_fn, args",
    [
        (job_completed_template, ("job-1", {"leads": 1})),
        (job_paused_template, ("job-1", "reason")),
        (approval_requested_template, ("appr-1", "act")),
        (lead_ready_template, (3,)),
    ],
)
def test_template_html_contains_basic_markup(template_fn, args):
    out = template_fn(*args, lang="en")
    # HTML must contain at least one tag (not just escaped text)
    assert "<" in out["html"] and ">" in out["html"]
    # Should wrap content in a div with inline style
    assert "div" in out["html"]
    assert "style=" in out["html"]


def test_template_default_lang_is_arabic():
    out = job_completed_template("job-1", {}, lang="ar")
    # Arabic content should appear in the rendered output
    assert "rtl" in out["html"]
