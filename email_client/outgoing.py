"""Immutable values shared by outgoing-mail previews and SMTP delivery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreparedAttachment:
    """An attachment snapshot captured while an outgoing message is prepared."""

    path: Path
    filename: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class PreparedEmail:
    """A validated, immutable message ready for preview or one SMTP attempt."""

    sender: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    subject: str
    text: str
    attachments: tuple[PreparedAttachment, ...] = ()
    in_reply_to: str | None = None
    references: str | None = None

    @property
    def preview_id(self) -> str:
        """Return a stable digest of all user-visible and send-relevant values."""
        canonical = {
            "from": self.sender,
            "to": self.to,
            "cc": self.cc,
            "bcc": self.bcc,
            "subject": self.subject,
            "text": self.text,
            "attachments": [
                {
                    "path": str(attachment.path),
                    "filename": attachment.filename,
                    "size": len(attachment.content),
                    "sha256": attachment.sha256,
                }
                for attachment in self.attachments
            ],
            "in_reply_to": self.in_reply_to,
            "references": self.references,
        }
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def preview(self) -> dict:
        """Return JSON-ready message details for user review."""
        return {
            "from": self.sender,
            "to": list(self.to),
            "cc": list(self.cc),
            "bcc": list(self.bcc),
            "subject": self.subject,
            "text": self.text,
            "attachments": [str(attachment.path) for attachment in self.attachments],
            "attachment_details": [
                {
                    "path": str(attachment.path),
                    "filename": attachment.filename,
                    "size": len(attachment.content),
                    "sha256": attachment.sha256,
                }
                for attachment in self.attachments
            ],
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "preview_id": self.preview_id,
        }
