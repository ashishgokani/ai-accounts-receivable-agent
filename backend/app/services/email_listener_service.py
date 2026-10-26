"""
Inbound Email Listener Service.

Connects to Gmail via IMAP SSL (Port 993) or Gmail API with OAuth 2.0 to monitor
incoming emails, inspect unread customer replies, and pass them to the
AI Reply Processor for semantic classification and approval routing.
Includes safe credential handling and mock simulation fallback.
"""

import email
from email.header import decode_header
import imaplib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import ist_now
from app.db.models import Customer
from app.services.ai_reply_processor import process_inbound_customer_email

logger = logging.getLogger(__name__)


def _decode_mime_header(header_value: Optional[str]) -> str:
    """Safely decodes RFC 2047 MIME encoded email headers into clean unicode strings."""
    if not header_value:
        return ""
    decoded_fragments = []
    for fragment, encoding in decode_header(header_value):
        if isinstance(fragment, bytes):
            decoded_fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded_fragments.append(str(fragment))
    return "".join(decoded_fragments).strip()


def _extract_email_body(msg: email.message.Message) -> str:
    """Extracts plain text body from MIME multipart or singlepart email message."""
    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text += payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body_text = payload.decode(charset, errors="replace")

    return body_text.strip()


class InboundEmailListener:
    """
    Manages detection and ingestion of inbound customer emails.
    """

    @classmethod
    def _get_last_run_time(cls, db: Session) -> Optional[datetime]:
        """Retrieves last autonomous scheduler execution timestamp from memory or DB."""
        try:
            from app.services.scheduler import automation_scheduler
            if automation_scheduler.last_run_at:
                return automation_scheduler.last_run_at
        except Exception:
            pass

        try:
            from app.db.models import SystemSetting
            row = db.query(SystemSetting).filter(SystemSetting.key == "scheduler_state").first()
            if row and row.value:
                state = json.loads(row.value)
                raw = state.get("last_run_at")
                if raw:
                    return datetime.fromisoformat(raw)
        except Exception:
            pass
        return None

    @classmethod
    def check_inbox_and_process(cls, db: Session) -> Dict[str, Any]:
        """
        Polls the configured mailbox, retrieves unseen messages, and processes them.
        Returns execution summary.
        """
        user = settings.imap_user or settings.smtp_user
        password = settings.imap_password or settings.smtp_password

        # If credentials are not supplied, return clean simulated status
        if not (user and password and settings.imap_polling_enabled):
            return {
                "status": "IDLE",
                "mode": "SIMULATION_FALLBACK",
                "processed_count": 0,
                "message": "IMAP credentials not configured. Inbound email listener operating in simulation/mock mode.",
            }

        processed_count = 0
        error_count = 0
        mail = None

        try:
            # 1. Connect to IMAP SSL server
            mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=15)
            mail.login(user, password)
            mail.select("INBOX")

            # 2. Determine cutoff time: only inspect emails received since the last agent run
            last_run = cls._get_last_run_time(db)
            now = ist_now()
            # Safety buffer of 2 minutes to prevent edge-case race conditions
            cutoff_time = (last_run - timedelta(minutes=2)) if last_run else (now - timedelta(hours=24))
            imap_since_date = cutoff_time.strftime("%d-%b-%Y")

            logger.info("IMAP listener searching messages since %s (cutoff: %s)", imap_since_date, cutoff_time.isoformat())

            # Search messages arriving on or after the cutoff date
            status_since, resp_since = mail.search(None, "SINCE", imap_since_date)

            candidate_ids = set()
            if status_since == "OK" and resp_since and resp_since[0]:
                candidate_ids.update(resp_since[0].split())

            if not candidate_ids:
                return {"status": "SUCCESS", "processed_count": 0, "message": "Inbox checked. No new messages found since last run."}

            # Cap to latest 25 messages to maintain rapid sub-second polling execution
            all_sorted_ids = sorted(list(candidate_ids), key=lambda x: int(x))
            msg_ids = all_sorted_ids[-25:]
            logger.info("Scanning %d latest inbox messages (out of %d since %s).", len(msg_ids), len(all_sorted_ids), imap_since_date)

            consecutive_older = 0
            # Check newest messages first in reverse order; stop scanning once messages precede cutoff
            for m_id in reversed(msg_ids):
                try:
                    # 1. Fast lightweight header peek (only ~200 bytes, includes Date for precise timestamp filtering)
                    res, header_data = mail.fetch(m_id, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
                    if res != "OK" or not header_data or not header_data[0]:
                        continue

                    raw_headers = header_data[0][1]
                    header_msg = email.message_from_bytes(raw_headers)
                    message_id = header_msg.get("Message-ID")

                    # Check email arrival Date against exact last agent run cutoff
                    date_header = header_msg.get("Date")
                    if date_header:
                        try:
                            msg_dt = email.utils.parsedate_to_datetime(date_header)
                            msg_utc = msg_dt.astimezone(timezone.utc) if msg_dt.tzinfo else msg_dt.replace(tzinfo=timezone.utc)
                            cutoff_utc = cutoff_time.astimezone(timezone.utc) if cutoff_time.tzinfo else cutoff_time.replace(tzinfo=timezone.utc)
                            if msg_utc < cutoff_utc:
                                consecutive_older += 1
                                if consecutive_older >= 3:
                                    # Monotonic sequence order: stop scanning once older than cutoff
                                    break
                                continue
                            else:
                                consecutive_older = 0
                        except Exception:
                            pass

                    # Deduplication check: if already processed, skip immediately
                    if message_id:
                        from app.db.models import InboundEmailLog
                        already_logged = db.query(InboundEmailLog.id).filter(InboundEmailLog.message_id == message_id).first()
                        if already_logged:
                            continue

                    from_header = _decode_mime_header(header_msg.get("From"))
                    sender_address = email.utils.parseaddr(from_header)[1].lower().strip()

                    if not sender_address:
                        continue

                    # 2. Strict Customer Check: If sender is not a registered customer, skip instantly
                    cust = db.query(Customer).filter(Customer.email.ilike(sender_address)).first()
                    if not cust:
                        continue

                    # 3. Sender IS a verified customer: Fetch full body and process with AI
                    res, data = mail.fetch(m_id, "(RFC822)")
                    if res != "OK" or not data:
                        continue

                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    message_id = msg.get("Message-ID")
                    to_header = _decode_mime_header(msg.get("To"))
                    subject = _decode_mime_header(msg.get("Subject"))
                    body = _extract_email_body(msg)

                    process_inbound_customer_email(
                        db=db,
                        sender_email=sender_address,
                        subject=subject,
                        raw_body=body,
                        message_id=message_id,
                        recipient_email=to_header,
                    )
                    processed_count += 1
                    mail.store(m_id, "+FLAGS", "\\Seen")

                except Exception as msg_err:
                    logger.error("Error processing single inbound message ID %s: %s", m_id, msg_err)
                    error_count += 1

            return {
                "status": "SUCCESS",
                "processed_count": processed_count,
                "error_count": error_count,
                "message": f"Processed {processed_count} inbound emails successfully.",
            }

        except Exception as conn_err:
            logger.warning("Could not poll IMAP mailbox: %s. Operating in simulation mode.", conn_err)
            return {
                "status": "CONNECTION_FAILED",
                "error": str(conn_err),
                "processed_count": 0,
            }
        finally:
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass


# Global singleton listener instance
inbound_email_listener = InboundEmailListener()
