"""Email find / verify pool.

Verification is NOT SMTP-only. Pipeline: syntax -> domain/MX -> disposable
-> role account -> provider verifier (Hunter/Abstract) -> SMTP with
catch-all detection. Results are 5-state, never just valid/invalid:

DELIVERABLE | RISKY | CATCH_ALL | INVALID | UNKNOWN

A domain that accepts any address (catch-all) is never marked DELIVERABLE.
"""
import re
import smtplib
import socket
from email.utils import parseaddr

from .base import BaseProvider, random_local_part

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "temp-mail.org",
    "yopmail.com", "throwawaymail.com", "getnada.com", "trashmail.com",
}

ROLE_ACCOUNTS = {
    "info", "sales", "contact", "admin", "administrator", "office", "hello",
    "support", "careers", "hr", "booking", "appointments", "marketing",
    "enquiries", "inquiries", "reception", "frontdesk", "email",
}

STATUS_DELIVERABLE = "DELIVERABLE"
STATUS_RISKY = "RISKY"
STATUS_CATCH_ALL = "CATCH_ALL"
STATUS_INVALID = "INVALID"
STATUS_UNKNOWN = "UNKNOWN"


def mx_hosts(domain: str):
    """MX lookup; falls back to A record (some domains accept mail without MX)."""
    try:
        import dns.resolver
    except ImportError:
        return None  # dnspython not installed -> cannot check
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return sorted((r.preference, str(r.exchange).rstrip(".")) for r in answers)
    except Exception:
        try:
            socket.gethostbyname(domain)
            return [(0, domain)]  # A-record fallback
        except OSError:
            return []


class HunterProvider(BaseProvider):
    name = "hunter"
    ptype = "email"
    tasks = ("email_verify", "email_find")
    env_key = "HUNTER_API_KEY"

    def request(self, task, payload):
        return self.verify(payload["email"]) if task == "email_verify" else self.find(payload["domain"])

    def verify(self, email: str) -> dict:
        data = self._json(self._http(
            "GET", "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": self.api_key},
        )).get("data", {})
        result = data.get("result", "unknown")
        score = float(data.get("score", 0)) / 100.0
        mapping = {
            "valid": (STATUS_DELIVERABLE, score),
            "risky": (STATUS_RISKY, min(score, 0.5)),
            "invalid": (STATUS_INVALID, 0.9),
            "unknown": (STATUS_UNKNOWN, 0.2),
        }
        status, confidence = mapping.get(result, (STATUS_UNKNOWN, 0.2))
        if data.get("status") in ("catch_all", "webmail_disposable"):
            status, confidence = STATUS_CATCH_ALL, 0.3
        return {"provider": self.name, "status": status, "confidence": confidence,
                "details": {"hunter_result": result, "score": score}, "units": 1}

    def find(self, domain: str) -> dict:
        data = self._json(self._http(
            "GET", "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "limit": 3, "api_key": self.api_key},
        )).get("data", {})
        emails = [
            {"value": e.get("value"), "type": e.get("type"),
             "first_name": e.get("first_name"), "last_name": e.get("last_name"),
             "position": e.get("position")}
            for e in data.get("emails", [])
        ]
        return {"provider": self.name, "emails": emails, "units": 1}


class AbstractProvider(BaseProvider):
    name = "abstract"
    ptype = "email"
    tasks = ("email_verify",)
    env_key = "ABSTRACT_API_KEY"

    def request(self, task, payload):
        data = self._json(self._http(
            "GET", "https://emailvalidation.abstractapi.com/v1/",
            params={"api_key": self.api_key, "email": payload["email"]},
        ))
        if data.get("is_disposable_email"):
            status, conf = STATUS_INVALID, 0.85
        elif not data.get("is_valid_format"):
            status, conf = STATUS_INVALID, 0.95
        elif data.get("is_role_email"):
            status, conf = STATUS_RISKY, 0.45
        else:
            quality = float(data.get("quality_score") or 0)
            status = STATUS_DELIVERABLE if quality >= 0.7 else STATUS_RISKY
            conf = max(quality, 0.3)
        return {"provider": self.name, "status": status, "confidence": conf,
                "details": {k: data.get(k) for k in
                            ("is_valid_format", "is_disposable_email", "is_role_email",
                             "quality_score")}, "units": 1}


class LocalSMTPVerifier(BaseProvider):
    """Last-resort verifier. Needs outbound port 25; in many networks this
    returns UNKNOWN — that is honest, better than a wrong DELIVERABLE."""
    name = "local_smtp"
    ptype = "email"
    tasks = ("email_verify",)
    env_key = None

    def request(self, task, payload):
        return self.verify(payload["email"])

    def verify(self, email: str) -> dict:
        cfg = (self.settings.get("verification", {}) or {})
        timeout = cfg.get("smtp_timeout", 10)
        probe_catch_all = cfg.get("catch_all_probe", True)
        mail_from = cfg.get("mail_from", "lead-engine@localhost")

        _, _, domain = email.rpartition("@")
        mx = mx_hosts(domain)
        if mx is None:
            return {"provider": self.name, "status": STATUS_UNKNOWN, "confidence": 0.1,
                    "details": {"reason": "mx_lookup_unavailable"}, "units": 0}
        if not mx:
            return {"provider": self.name, "status": STATUS_INVALID, "confidence": 0.9,
                    "details": {"reason": "no_mx_record"}, "units": 0}

        host = mx[0][1]
        try:
            with smtplib.SMTP(timeout=timeout) as smtp:
                smtp.ehlo_or_helo_if_needed()
                code, _ = smtp.docmd("MAIL", f"FROM:<{mail_from}>")
                if code != 250:
                    return {"provider": self.name, "status": STATUS_UNKNOWN, "confidence": 0.2,
                            "details": {"reason": f"mail_from_rejected_{code}"}, "units": 0}
                code, _ = smtp.docmd("RCPT", f"TO:<{email}>")
                if code in (450, 451, 452):
                    return {"provider": self.name, "status": STATUS_UNKNOWN, "confidence": 0.2,
                            "details": {"reason": "greylisted"}, "units": 0}
                if code != 250:
                    return {"provider": self.name, "status": STATUS_INVALID, "confidence": 0.85,
                            "details": {"reason": f"rcpt_rejected_{code}"}, "units": 0}
                if probe_catch_all:
                    code_rand, _ = smtp.docmd(
                        "RCPT", f"TO:<{random_local_part()}@{domain}>")
                    if code_rand == 250:
                        return {"provider": self.name, "status": STATUS_CATCH_ALL,
                                "confidence": 0.3,
                                "details": {"reason": "catch_all_domain"}, "units": 0}
                return {"provider": self.name, "status": STATUS_DELIVERABLE,
                        "confidence": 0.75, "details": {"reason": "smtp_accepted"}, "units": 0}
        except (smtplib.SMTPException, OSError) as exc:
            return {"provider": self.name, "status": STATUS_UNKNOWN, "confidence": 0.15,
                    "details": {"reason": f"smtp_unreachable: {exc.__class__.__name__}"}, "units": 0}


class VerificationPipeline:
    """Runs the ordered checks; provider verifiers go through the router
    so quota/fallback logic applies here too."""

    def __init__(self, router):
        self.router = router

    def verify(self, email: str) -> dict:
        email = (email or "").strip().lower()
        _, _, domain = email.rpartition("@")

        if not EMAIL_RE.match(email) or parseaddr(email)[1] != email:
            return self._result(STATUS_INVALID, 0.99, "syntax", "syntax")
        if domain in DISPOSABLE_DOMAINS:
            return self._result(STATUS_INVALID, 0.9, "disposable_domain", "disposable")
        if email.rpartition("@")[0] in ROLE_ACCOUNTS:
            base = self._via_provider(email)
            if base["status"] == STATUS_DELIVERABLE:
                base = self._result(STATUS_RISKY, min(base["confidence"], 0.5),
                                    "role_account", "role_account", base["provider"])
            return base
        return self._via_provider(email)

    def _via_provider(self, email: str) -> dict:
        try:
            result, meta = self.router.route("email_verify", {"email": email},
                                             cache_data_type="email_verification")
        except Exception as exc:  # NoProviderAvailable or anything else
            return self._result(STATUS_UNKNOWN, 0.1, f"no_verifier: {exc}", "none")
        result = dict(result)
        result["via"] = meta.get("provider")
        if meta.get("provider") == "cache":
            result["via"] = "cache"
        return result

    @staticmethod
    def _result(status, confidence, reason, method, provider="pipeline"):
        return {"provider": provider, "status": status, "confidence": confidence,
                "details": {"reason": reason}, "method": method, "units": 0}
