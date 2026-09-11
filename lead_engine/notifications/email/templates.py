"""Pre-built bilingual (AR/EN) notification templates.

Every template returns ``{"subject": str, "html": str, "text": str}`` and
can be handed straight to ``EmailSender.send``. ``lang="ar"`` (default)
produces Arabic-first content with RTL direction; ``lang="en"`` produces
English-first LTR content. Each template renders both languages internally
so the call site never has to pick strings.
"""
from __future__ import annotations

_FONT_FAMILY = "Segoe UI, Tahoma, Arial, sans-serif"

AR_FOOTER = "محرك العملاء المحتملين — Lead Engine"
EN_FOOTER = "Lead Engine"


def _wrap_html(title: str, paragraphs: list[str], lang: str) -> str:
    direction = "rtl" if lang == "ar" else "ltr"
    body = "\n".join(f"  <p>{p}</p>" for p in paragraphs)
    footer = AR_FOOTER if lang == "ar" else EN_FOOTER
    return (
        f'<div style="font-family: \'{_FONT_FAMILY}\'; '
        f'direction: {direction}; max-width: 560px; '
        f'padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; '
        f'background: #ffffff; color: #111827;">\n'
        f'  <h2 style="margin: 0 0 12px 0; font-size: 18px;">{title}</h2>\n'
        f"{body}\n"
        f'  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 16px 0;">\n'
        f'  <small style="color: #6b7280;">{footer}</small>\n'
        f"</div>"
    )


def _format_kv_lines(pairs: dict, bullet: str) -> str:
    if not pairs:
        return ""
    return "\n".join(f"  {bullet} {k}: {v}" for k, v in pairs.items())


def job_completed_template(job_id: str, metrics: dict, lang: str = "ar") -> dict:
    """Job finished successfully — surface the headline metrics."""
    metrics_lines = _format_kv_lines(metrics, "•" if lang == "ar" else "-")

    if lang == "ar":
        subject = f"اكتمل العمل: {job_id}"
        title = f"اكتمل العمل {job_id}"
        paragraphs = [f"تم الانتهاء من العمل <b>{job_id}</b> بنجاح."]
        if metrics_lines:
            paragraphs.append("المقاييس الرئيسية:")
            for k, v in metrics.items():
                paragraphs.append(f"&nbsp;&nbsp;• {k}: <b>{v}</b>")
        text = f"اكتمل العمل {job_id} بنجاح.\n"
        if metrics_lines:
            text += "\nالمقاييس الرئيسية:\n" + metrics_lines
    else:
        subject = f"Job completed: {job_id}"
        title = f"Job {job_id} completed"
        paragraphs = [f"Job <b>{job_id}</b> finished successfully."]
        if metrics_lines:
            paragraphs.append("Headline metrics:")
            for k, v in metrics.items():
                paragraphs.append(f"&nbsp;&nbsp;• {k}: <b>{v}</b>")
        text = f"Job {job_id} finished successfully.\n"
        if metrics_lines:
            text += "\nHeadline metrics:\n" + metrics_lines

    return {"subject": subject, "html": _wrap_html(title, paragraphs, lang), "text": text}


def job_paused_template(job_id: str, reason: str, lang: str = "ar") -> dict:
    """Job paused — needs human/system attention to resume."""
    if lang == "ar":
        subject = f"العمل متوقف مؤقتاً: {job_id}"
        title = f"العمل {job_id} متوقف"
        paragraphs = [
            f"العمل <b>{job_id}</b> متوقف مؤقتاً وينتظر مراجعة.",
            f"<b>السبب:</b> {reason}",
            "يمكنك مراجعته من لوحة التحكم واستئنافه عند الجاهزية.",
        ]
        text = (
            f"العمل {job_id} متوقف مؤقتاً وينتظر مراجعة.\n"
            f"السبب: {reason}\n"
            "راجع لوحة التحكم واستأنف العمل عند الجاهزية."
        )
    else:
        subject = f"Job paused: {job_id}"
        title = f"Job {job_id} paused"
        paragraphs = [
            f"Job <b>{job_id}</b> has been paused and needs review.",
            f"<b>Reason:</b> {reason}",
            "Open the control plane to inspect and resume when ready.",
        ]
        text = (
            f"Job {job_id} has been paused and needs review.\n"
            f"Reason: {reason}\n"
            "Open the control plane to inspect and resume when ready."
        )

    return {"subject": subject, "html": _wrap_html(title, paragraphs, lang), "text": text}


def approval_requested_template(approval_id: str, action: str, lang: str = "ar") -> dict:
    """An approval item is waiting for a human decision."""
    if lang == "ar":
        subject = f"بانتظار الموافقة: {action}"
        title = f"بانتظار الموافقة على {action}"
        paragraphs = [
            f"العنصر <b>{approval_id}</b> في انتظار قرار.",
            f"<b>الإجراء المطلوب:</b> {action}",
            "يرجى المراجعة والبت في الطلب من لوحة التحكم.",
        ]
        text = (
            f"العنصر {approval_id} في انتظار قرار.\n"
            f"الإجراء المطلوب: {action}\n"
            "راجع لوحة التحكم وخذ القرار المناسب."
        )
    else:
        subject = f"Approval requested: {action}"
        title = f"Approval needed for {action}"
        paragraphs = [
            f"Item <b>{approval_id}</b> is awaiting a decision.",
            f"<b>Action:</b> {action}",
            "Please review and approve or reject from the control plane.",
        ]
        text = (
            f"Item {approval_id} is awaiting a decision.\n"
            f"Action: {action}\n"
            "Please review and approve or reject from the control plane."
        )

    return {"subject": subject, "html": _wrap_html(title, paragraphs, lang), "text": text}


def lead_ready_template(lead_count: int, lang: str = "ar") -> dict:
    """A batch of leads is ready for downstream consumption."""
    if lang == "ar":
        subject = f"عملاء جدد جاهزون ({lead_count})"
        title = f"{lead_count} عميل جديد جاهز"
        paragraphs = [
            f"تم تجهيز <b>{lead_count}</b> عميل جديد للتسليم.",
            "يمكنك تنزيل القائمة أو تمريرها إلى الخطوة التالية.",
        ]
        text = (
            f"تم تجهيز {lead_count} عميل جديد للتسليم.\n"
            "نزّل القائمة من لوحة التحكم أو مرّرها إلى الخطوة التالية."
        )
    else:
        subject = f"Leads ready ({lead_count})"
        title = f"{lead_count} new leads ready"
        paragraphs = [
            f"<b>{lead_count}</b> new leads are ready for delivery.",
            "Download the batch from the control plane or hand it off downstream.",
        ]
        text = (
            f"{lead_count} new leads are ready for delivery.\n"
            "Download the batch from the control plane or hand it off downstream."
        )

    return {"subject": subject, "html": _wrap_html(title, paragraphs, lang), "text": text}
