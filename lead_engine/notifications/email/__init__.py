"""Email notification channel — SMTP sender + bilingual templates."""
from .sender import EmailSender
from .templates import (
    approval_requested_template,
    job_completed_template,
    job_paused_template,
    lead_ready_template,
)

__all__ = [
    "EmailSender",
    "approval_requested_template",
    "job_completed_template",
    "job_paused_template",
    "lead_ready_template",
]
