"""
email_service.py
----------------
SMTP email sending service.

Reads SMTP credentials at call-time (not at import-time) so that
load_dotenv() in send_reminders.py or main.py always takes effect
before the credentials are resolved.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import List, Optional, Union

logger = logging.getLogger("digitaldrm.email")


def _smtp_cfg():
    """Read SMTP settings from environment at call-time, not at import-time."""
    return {
        "host":       os.getenv("SMTP_HOST", "").strip(),
        "port":       int(os.getenv("SMTP_PORT", "587")),
        "user":       os.getenv("SMTP_USER", "").strip(),
        "password":   os.getenv("SMTP_PASSWORD", "").strip(),
        "use_tls":    os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"),
        "from_email": os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER", "")).strip(),
        "from_name":  os.getenv("SMTP_FROM_NAME", "DigitalDRM").strip(),
    }


def send_email(
    to_email: Union[str, List[str]],
    subject: str,
    body: str,
    cc: Optional[Union[str, List[str]]] = None,
    html_body: Optional[str] = None,
) -> bool:
    """
    Sends an email to one or more recipients (and, optionally, CC
    recipients) in a single SMTP transaction. Returns True on success,
    False on failure. Never raises.

    `cc` is optional and defaults to None so every existing call site
    that doesn't pass it keeps working exactly as before.

    `html_body` is optional and defaults to None. When provided, the
    message is sent as multipart/alternative with BOTH the plain-text
    `body` and the `html_body` attached, so mail clients that support
    HTML render the rich version while plain-text clients still get a
    readable fallback. When omitted, behavior is identical to before
    (plain text only) — existing call sites that don't pass html_body
    keep working exactly as before.
    """
    cfg = _smtp_cfg()

    # ── Step 1: validate SMTP config ────────────────────────────────────────
    missing = [k for k in ("host", "user", "password") if not cfg[k]]
    if missing:
        logger.error(
            "[EMAIL] SMTP config incomplete – missing: %s. "
            "Check SMTP_HOST / SMTP_USER / SMTP_PASSWORD in .env. Email NOT sent.",
            ", ".join(missing),
        )
        return False

    # ── Step 2: normalise recipient / cc lists ──────────────────────────────
    recipients: List[str] = (
        [to_email] if isinstance(to_email, str) else list(to_email)
    )
    recipients = [r.strip() for r in recipients if r.strip()]
    if not recipients:
        logger.error("[EMAIL] Empty recipient list. Email NOT sent.")
        return False

    cc_list: List[str] = []
    if cc:
        cc_list = [cc] if isinstance(cc, str) else list(cc)
        cc_list = [c.strip() for c in cc_list if c.strip()]

    logger.info(
        "[EMAIL] Preparing to send | To: [%s]%s | Subject: %s%s",
        ", ".join(recipients),
        f" | CC: [{', '.join(cc_list)}]" if cc_list else "",
        subject,
        " | (html)" if html_body else "",
    )
    logger.info(
        "[EMAIL] SMTP: host=%s port=%s user=%s tls=%s",
        cfg["host"], cfg["port"], cfg["user"], cfg["use_tls"],
    )

    # ── Step 3: build message ───────────────────────────────────────────────
    # If an HTML alternative is supplied, the message must be
    # multipart/alternative (plain text + html as siblings) so mail
    # clients pick ONE version to render rather than showing both
    # stacked on top of each other. Plain-text-only messages keep using
    # the plain "mixed" container exactly as before.
    msg = MIMEMultipart("alternative") if html_body else MIMEMultipart()
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
    msg["To"] = ", ".join(recipients)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject

    # Plain text first, HTML second — per MIME convention for
    # multipart/alternative, clients should render the LAST part they
    # understand, so the richer HTML version goes last.
    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    # All actual recipients for the SMTP transaction envelope — CC
    # addresses must be included here too, or they'll be silently
    # dropped even though the "Cc" header shows them.
    envelope_recipients = recipients + cc_list

    # ── Step 4: send ────────────────────────────────────────────────────────
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            server.set_debuglevel(0)
            if cfg["use_tls"]:
                logger.info("[EMAIL] Starting TLS…")
                server.starttls()
            logger.info("[EMAIL] Logging in as %s…", cfg["user"])
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_email"], envelope_recipients, msg.as_string())

        logger.info(
            "[EMAIL] ✅ Sent successfully | To: [%s]%s | Subject: %s",
            ", ".join(recipients),
            f" | CC: [{', '.join(cc_list)}]" if cc_list else "",
            subject,
        )
        return True

    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "[EMAIL] ❌ Authentication failed for user=%s | %s", cfg["user"], exc
        )
    except smtplib.SMTPConnectError as exc:
        logger.error(
            "[EMAIL] ❌ Cannot connect to SMTP host=%s port=%s | %s",
            cfg["host"], cfg["port"], exc,
        )
    except smtplib.SMTPException as exc:
        logger.error("[EMAIL] ❌ SMTP error | %s", exc)
    except OSError as exc:
        logger.error(
            "[EMAIL] ❌ Network error reaching %s:%s | %s",
            cfg["host"], cfg["port"], exc,
        )
    except Exception as exc:
        logger.error("[EMAIL] ❌ Unexpected error | %s", exc, exc_info=True)

    return False


def send_email_with_attachment(
    to_email: Union[str, List[str]],
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
    cc: Optional[Union[str, List[str]]] = None,
    html_body: Optional[str] = None,
) -> bool:
    """
    Same behavior/config/logging as send_email(), but with a single
    binary file attached (e.g. a generated PDF report). Returns True on
    success, False on failure. Never raises — callers can safely fire
    this after a report is generated without risking the calling
    operation itself.

    `cc` and `html_body` behave exactly as in send_email() and both
    default to None, so existing call sites keep working unchanged.
    """
    cfg = _smtp_cfg()

    missing = [k for k in ("host", "user", "password") if not cfg[k]]
    if missing:
        logger.error(
            "[EMAIL] SMTP config incomplete – missing: %s. "
            "Check SMTP_HOST / SMTP_USER / SMTP_PASSWORD in .env. Email NOT sent.",
            ", ".join(missing),
        )
        return False

    recipients: List[str] = (
        [to_email] if isinstance(to_email, str) else list(to_email)
    )
    recipients = [r.strip() for r in recipients if r.strip()]
    if not recipients:
        logger.error("[EMAIL] Empty recipient list. Email NOT sent.")
        return False

    cc_list: List[str] = []
    if cc:
        cc_list = [cc] if isinstance(cc, str) else list(cc)
        cc_list = [c.strip() for c in cc_list if c.strip()]

    logger.info(
        "[EMAIL] Preparing to send (with attachment) | To: [%s]%s | Subject: %s | Attachment: %s (%d bytes)%s",
        ", ".join(recipients),
        f" | CC: [{', '.join(cc_list)}]" if cc_list else "",
        subject,
        attachment_filename,
        len(attachment_bytes) if attachment_bytes else 0,
        " | (html)" if html_body else "",
    )
    logger.info(
        "[EMAIL] SMTP: host=%s port=%s user=%s tls=%s",
        cfg["host"], cfg["port"], cfg["user"], cfg["use_tls"],
    )

    # Outer container is always "mixed" (attachment + body parts), and
    # when there's an HTML alternative, the text/html pair is nested
    # inside its own "alternative" sub-part so mail clients pick one
    # body version to render while still showing the attachment.
    msg = MIMEMultipart("mixed")
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
    msg["To"] = ", ".join(recipients)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject

    if html_body:
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(body, "plain"))
        body_part.attach(MIMEText(html_body, "html"))
        msg.attach(body_part)
    else:
        msg.attach(MIMEText(body, "plain"))

    try:
        part = MIMEApplication(attachment_bytes, Name=attachment_filename)
        part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
        msg.attach(part)
    except Exception as exc:
        logger.error("[EMAIL] ❌ Could not attach file %s | %s", attachment_filename, exc)
        return False

    envelope_recipients = recipients + cc_list

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            server.set_debuglevel(0)
            if cfg["use_tls"]:
                logger.info("[EMAIL] Starting TLS…")
                server.starttls()
            logger.info("[EMAIL] Logging in as %s…", cfg["user"])
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_email"], envelope_recipients, msg.as_string())

        logger.info(
            "[EMAIL] ✅ Sent successfully (with attachment) | To: [%s]%s | Subject: %s",
            ", ".join(recipients),
            f" | CC: [{', '.join(cc_list)}]" if cc_list else "",
            subject,
        )
        return True

    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "[EMAIL] ❌ Authentication failed for user=%s | %s", cfg["user"], exc
        )
    except smtplib.SMTPConnectError as exc:
        logger.error(
            "[EMAIL] ❌ Cannot connect to SMTP host=%s port=%s | %s",
            cfg["host"], cfg["port"], exc,
        )
    except smtplib.SMTPException as exc:
        logger.error("[EMAIL] ❌ SMTP error | %s", exc)
    except OSError as exc:
        logger.error(
            "[EMAIL] ❌ Network error reaching %s:%s | %s",
            cfg["host"], cfg["port"], exc,
        )
    except Exception as exc:
        logger.error("[EMAIL] ❌ Unexpected error | %s", exc, exc_info=True)

    return False