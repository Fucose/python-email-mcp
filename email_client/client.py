"""High-level email client that combines IMAP and SMTP operations."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .config import Config, get_default_download_dir
from .errors import EmailClientError, NotFoundError
from .imap_client import IMAPClient
from .models import Email
from .outgoing import PreparedEmail
from .smtp_client import SMTPClient


class EmailClient:
    """A short-lived email client suitable for one CLI or MCP operation."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.config.load_config()
        self.imap_client: Optional[IMAPClient] = None
        self.smtp_client: Optional[SMTPClient] = None

    def test_connection(self, test_type: str = "both") -> dict:
        """Test selected protocols and return non-secret structured results."""
        results: dict[str, dict] = {}
        if test_type in ("imap", "both"):
            results["imap"] = self._test_protocol("imap")
        if test_type in ("smtp", "both"):
            results["smtp"] = self._test_protocol("smtp")
        return results

    def get_recent_emails(self, days: int = 3, limit: int = 20) -> List[Email]:
        return self._imap().get_recent_emails(days, limit)

    def search_emails(self, subject: str, days: int = 7) -> List[Email]:
        return self._imap().search_by_subject(subject, days)

    def get_email(self, uid: str) -> Optional[Email]:
        return self._imap().get_email_content(uid)

    def download_attachments(
        self,
        uid: str,
        folder: Optional[Path] = None,
    ) -> List[Path]:
        destination = folder or get_default_download_dir()
        return self._imap().download_attachments(uid, destination)

    def batch_download_attachments(
        self,
        subject: str,
        days: int = 7,
        folder: Optional[Path] = None,
    ) -> List[Path]:
        emails = self.search_emails(subject, days)
        destination = folder or get_default_download_dir()
        return self._imap().batch_download_attachments(
            [message.uid for message in emails], destination
        )

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> bool:
        return self._smtp().send_email(to, subject, body, attachments, cc, bcc)

    def prepare_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> PreparedEmail:
        return self._smtp().prepare_email(to, subject, body, attachments, cc, bcc)

    def prepare_reply(
        self,
        uid: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        reply_all: bool = False,
    ) -> PreparedEmail:
        original_email = self.get_email(uid)
        if not original_email:
            raise NotFoundError(f"Email UID {uid} was not found")
        return self._smtp().prepare_reply(original_email, body, attachments, reply_all)

    def send_prepared_email(self, plan: PreparedEmail) -> bool:
        return self._smtp().send_prepared_email(plan)

    def reply(
        self,
        uid: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        reply_all: bool = False,
    ) -> bool:
        plan = self.prepare_reply(uid, body, attachments, reply_all)
        return self.send_prepared_email(plan)

    def disconnect(self) -> None:
        """Close all open connections; safe to call more than once."""
        if self.imap_client:
            self.imap_client.disconnect()
            self.imap_client = None
        if self.smtp_client:
            self.smtp_client.disconnect()
            self.smtp_client = None

    def _imap(self) -> IMAPClient:
        if self.imap_client is None:
            host, port, user, password, use_ssl = self.config.get_imap_config()
            candidate = IMAPClient(host, port, user, password, use_ssl)
            self.imap_client = candidate
        return self.imap_client

    def _smtp(self) -> SMTPClient:
        if self.smtp_client is None:
            host, port, user, password, use_ssl = self.config.get_smtp_config()
            candidate = SMTPClient(host, port, user, password, use_ssl)
            signature = self.config.load_signature()
            if signature:
                candidate.set_signature(signature)
            self.smtp_client = candidate
        return self.smtp_client

    def _test_protocol(self, protocol: str) -> dict:
        try:
            if protocol == "imap":
                self._imap().connect()
            else:
                self._smtp().connect()
            return {"ok": True, "code": None, "message": f"{protocol.upper()} connection succeeded"}
        except EmailClientError as exc:
            return {"ok": False, "code": exc.code, "message": str(exc)}
        finally:
            if protocol == "imap" and self.imap_client:
                self.imap_client.disconnect()
                self.imap_client = None
            if protocol == "smtp" and self.smtp_client:
                self.smtp_client.disconnect()
                self.smtp_client = None
