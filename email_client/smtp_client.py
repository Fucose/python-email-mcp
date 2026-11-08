"""SMTP connection and outgoing message preparation/delivery."""

from __future__ import annotations

import logging
import re
import smtplib
import ssl as ssl_module
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import getaddresses
from pathlib import Path
from typing import Iterable, List, Optional

from .errors import (
    AuthenticationError,
    DeliveryError,
    InvalidArgumentError,
    TransportError,
)
from .models import Email
from .outgoing import PreparedAttachment, PreparedEmail

LOGGER = logging.getLogger(__name__)


class SMTPClient:
    """Prepare messages without network access and send each plan once."""

    def __init__(self, host: str, port: int, user: str, password: str, ssl: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self.client: Optional[smtplib.SMTP] = None
        self.signature: Optional[str] = None

    def connect(self) -> bool:
        """Connect securely and authenticate only after TLS is established."""
        try:
            context = ssl_module.create_default_context()
            if self.ssl:
                self.client = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    context=context,
                )
            else:
                self.client = smtplib.SMTP(self.host, self.port)
                self.client.starttls(context=context)
        except Exception as exc:
            self.disconnect()
            raise TransportError(f"Unable to connect to SMTP server: {exc}") from exc

        try:
            self.client.login(self.user, self.password)
        except smtplib.SMTPAuthenticationError as exc:
            self.disconnect()
            raise AuthenticationError("SMTP authentication failed") from exc
        except Exception as exc:
            self.disconnect()
            raise TransportError(f"SMTP login failed: {exc}") from exc
        return True

    def disconnect(self) -> None:
        """Close the current SMTP connection, including after TLS errors."""
        client, self.client = self.client, None
        if client is None:
            return
        try:
            client.quit()
        except Exception:
            try:
                client.close()
            except Exception:
                pass

    def set_signature(self, signature: str) -> None:
        self.signature = signature

    def load_signature_from_file(self, signature_file: Path) -> bool:
        try:
            if signature_file.exists():
                self.signature = signature_file.read_text(encoding="utf-8").strip()
                return True
            return False
        except OSError as exc:
            LOGGER.warning("Unable to load signature file: %s", exc)
            return False

    def prepare_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        skip_signature: bool = False,
    ) -> PreparedEmail:
        """Validate and freeze all outgoing values without connecting to SMTP."""
        safe_subject = self._header_value(subject, "subject")
        if not isinstance(body, str):
            raise InvalidArgumentError("Email body must be text")
        text = body
        if self.signature and not skip_signature:
            text += "\n\n" + self.signature

        sender = self._header_value(self.user, "sender")
        sender_addresses = self._parse_addresses([sender], "sender")
        if len(sender_addresses) != 1:
            raise InvalidArgumentError("Sender must contain exactly one email address")

        to_addresses = self._parse_addresses(to, "to")
        cc_addresses = self._parse_addresses(cc, "cc")
        bcc_addresses = self._parse_addresses(bcc, "bcc")
        to_addresses, cc_addresses, bcc_addresses = self._unique_recipient_fields(
            to_addresses,
            cc_addresses,
            bcc_addresses,
        )
        if not to_addresses and not cc_addresses and not bcc_addresses:
            raise InvalidArgumentError("At least one recipient is required")

        snapshots = self._read_attachments(attachments)
        return PreparedEmail(
            sender=sender,
            to=tuple(to_addresses),
            cc=tuple(cc_addresses),
            bcc=tuple(bcc_addresses),
            subject=safe_subject,
            text=text,
            attachments=tuple(snapshots),
        )

    def prepare_reply(
        self,
        original_email: Email,
        body: str,
        attachments: Optional[List[Path]] = None,
        reply_all: bool = False,
    ) -> PreparedEmail:
        """Prepare a reply using Reply-To and preserve standard thread headers."""
        reply_to_value = self._header_value(
            original_email.reply_to,
            "Reply-To",
            allow_folding=True,
            optional=True,
        )
        reply_to = self._parse_addresses(
            [reply_to_value] if reply_to_value else [],
            "reply-to",
        )
        from_value = self._header_value(original_email.from_, "from", allow_folding=True)
        sender_addresses = reply_to or self._parse_addresses([from_value], "from")
        if not sender_addresses:
            raise InvalidArgumentError("The original message has no valid reply address")

        to_addresses = self._unique_addresses(sender_addresses, excluded=set())
        cc_addresses: list[str] = []
        if reply_all:
            own_address = self._parse_addresses([self.user], "sender")[0].casefold()
            original_to_value = self._header_value(
                original_email.to,
                "original to",
                allow_folding=True,
            )
            original_to = self._parse_addresses([original_to_value], "original to")
            original_cc_value = self._header_value(
                original_email.cc,
                "original cc",
                allow_folding=True,
                optional=True,
            )
            original_cc = self._parse_addresses(
                [original_cc_value] if original_cc_value else [],
                "original cc",
            )
            to_addresses = self._unique_addresses(
                [*sender_addresses, *original_to],
                excluded={own_address},
            )
            cc_addresses = self._unique_addresses(
                original_cc,
                excluded={own_address, *to_addresses},
            )
        if not to_addresses and not cc_addresses:
            raise InvalidArgumentError("The reply has no recipients")

        subject = self._header_value(original_email.subject, "subject")
        if not subject.upper().startswith("RE:"):
            subject = f"Re: {subject}"

        in_reply_to = self._header_value(
            original_email.message_id,
            "In-Reply-To",
            allow_folding=True,
            optional=True,
        )
        references = self._header_value(
            original_email.references,
            "References",
            allow_folding=True,
            optional=True,
        )
        if in_reply_to:
            reference_ids = references.split() if references else []
            for message_id in in_reply_to.split():
                if message_id not in reference_ids:
                    reference_ids.append(message_id)
            references = " ".join(reference_ids)

        sender = self._header_value(self.user, "sender")
        if len(self._parse_addresses([sender], "sender")) != 1:
            raise InvalidArgumentError("Sender must contain exactly one email address")
        return PreparedEmail(
            sender=sender,
            to=tuple(to_addresses),
            cc=tuple(cc_addresses),
            bcc=(),
            subject=subject,
            text=self._build_reply_text(original_email, body),
            attachments=tuple(self._read_attachments(attachments)),
            in_reply_to=in_reply_to,
            references=references,
        )

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        skip_signature: bool = False,
    ) -> bool:
        plan = self.prepare_email(to, subject, body, attachments, cc, bcc, skip_signature)
        return self.send_prepared_email(plan)

    def reply_email(
        self,
        original_email: Email,
        body: str,
        attachments: Optional[List[Path]] = None,
        reply_all: bool = False,
    ) -> bool:
        plan = self.prepare_reply(original_email, body, attachments, reply_all)
        return self.send_prepared_email(plan)

    def send_prepared_email(self, plan: PreparedEmail) -> bool:
        """Send one frozen plan and report refusal or uncertain outcomes."""
        if not isinstance(plan, PreparedEmail):
            raise InvalidArgumentError("A prepared email plan is required")

        msg = self._build_message(plan)
        recipients = [*plan.to, *plan.cc, *plan.bcc]
        if not recipients:
            raise InvalidArgumentError("At least one recipient is required")
        if not self.client:
            self.connect()

        try:
            refused = self.client.send_message(msg, to_addrs=recipients)
        except smtplib.SMTPRecipientsRefused as exc:
            self._raise_refused(plan, exc.recipients)
        except (smtplib.SMTPSenderRefused, smtplib.SMTPHeloError) as exc:
            response = (exc.smtp_code, exc.smtp_error)
            self._raise_refused(plan, {address: response for address in recipients})
        except smtplib.SMTPDataError as exc:
            response = self._response_parts((exc.smtp_code, exc.smtp_error))
            rejected = {address: response for address in recipients}
            self.disconnect()
            raise DeliveryError(
                status="rejected",
                accepted=[],
                rejected=rejected,
                unknown=[],
                message=f"SMTP rejected message data: {response['message']}",
            ) from exc
        except smtplib.SMTPAuthenticationError as exc:
            self.disconnect()
            raise AuthenticationError("SMTP authentication failed") from exc
        except Exception as exc:
            self.disconnect()
            raise DeliveryError(
                status="unknown",
                accepted=[],
                rejected={},
                unknown=recipients,
                message=f"SMTP send failed with an unknown delivery outcome: {exc}",
            ) from exc

        if refused:
            self._raise_refused(plan, refused)
        return True

    def _raise_refused(self, plan: PreparedEmail, refused: dict) -> None:
        rejected: dict[str, dict] = {}
        recipients = [*plan.to, *plan.cc, *plan.bcc]
        actual_by_key = {address.casefold(): address for address in recipients}
        for address, response in refused.items():
            normalized = self._normalize_address_key(address)
            actual = actual_by_key.get(normalized.casefold(), normalized)
            rejected[actual] = self._response_parts(response)
        rejected_keys = {address.casefold() for address in rejected}
        accepted = [address for address in recipients if address.casefold() not in rejected_keys]
        self.disconnect()
        status = "partial" if accepted else "rejected"
        raise DeliveryError(
            status=status,
            accepted=accepted,
            rejected=rejected,
            unknown=[],
            message="SMTP rejected one or more recipients",
        )

    @staticmethod
    def _response_parts(response) -> dict:
        if isinstance(response, (tuple, list)) and len(response) >= 2:
            code, message = response[0], response[1]
        else:
            code, message = 0, response
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 0
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")
        return {"code": code, "message": str(message)}

    @classmethod
    def _normalize_address_key(cls, address) -> str:
        if isinstance(address, bytes):
            address = address.decode("utf-8", errors="replace")
        try:
            parsed = cls._parse_addresses([str(address)], "SMTP response")
        except InvalidArgumentError:
            return str(address).strip()
        return parsed[0] if len(parsed) == 1 else str(address).strip()

    def _build_message(self, plan: PreparedEmail):
        try:
            sender_addresses = self._parse_addresses([plan.sender], "sender")
            if len(sender_addresses) != 1:
                raise InvalidArgumentError("Sender must contain exactly one email address")
            for field, values in (("to", plan.to), ("cc", plan.cc), ("bcc", plan.bcc)):
                parsed = self._parse_addresses(values, field)
                if parsed != list(values):
                    raise InvalidArgumentError(f"Email {field} recipients are not normalized")
            if not isinstance(plan.text, str):
                raise InvalidArgumentError("Email body must be text")
            if plan.attachments:
                msg = MIMEMultipart()
                msg.attach(MIMEText(plan.text, "plain", "utf-8"))
            else:
                msg = MIMEText(plan.text, "plain", "utf-8")

            msg["From"] = self._header_value(plan.sender, "sender")
            msg["To"] = ", ".join(plan.to)
            msg["Subject"] = self._header_value(plan.subject, "subject")
            if plan.cc:
                msg["Cc"] = ", ".join(plan.cc)
            if plan.in_reply_to:
                msg["In-Reply-To"] = self._header_value(
                    plan.in_reply_to,
                    "In-Reply-To",
                    allow_folding=True,
                )
            if plan.references:
                msg["References"] = self._header_value(
                    plan.references,
                    "References",
                    allow_folding=True,
                )

            for attachment in plan.attachments:
                if "\r" in attachment.filename or "\n" in attachment.filename:
                    raise InvalidArgumentError("Attachment filename contains a line break")
                part = MIMEApplication(attachment.content)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=attachment.filename,
                )
                msg.attach(part)
            return msg
        except InvalidArgumentError:
            raise
        except (TypeError, ValueError) as exc:
            raise InvalidArgumentError(f"Invalid outgoing email header or MIME value: {exc}") from exc

    @staticmethod
    def _header_value(
        value: str | None,
        name: str,
        *,
        allow_folding: bool = False,
        optional: bool = False,
    ) -> str | None:
        if value is None and optional:
            return None
        if not isinstance(value, str):
            raise InvalidArgumentError(f"Email {name} must be text")
        if allow_folding:
            value = re.sub(r"\r\n[ \t]+", " ", value)
        if any(char in value for char in "\r\n") or any(
            ord(char) < 32 or ord(char) == 127 for char in value
        ):
            raise InvalidArgumentError(f"Email {name} contains an invalid header character")
        value = value.strip()
        if not value and optional:
            return None
        return value

    @classmethod
    def _parse_addresses(cls, values: Iterable[str] | None, field: str) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        addresses: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise InvalidArgumentError(f"Email {field} recipients must be text")
            if "\r" in value or "\n" in value:
                raise InvalidArgumentError(f"Email {field} contains a line break")
            parsed = getaddresses([value])
            if not parsed:
                raise InvalidArgumentError(f"Email {field} contains an invalid address")
            for _, address in parsed:
                address = address.strip()
                if not cls._valid_address(address):
                    raise InvalidArgumentError(f"Email {field} contains an invalid address")
                addresses.append(address)
        return addresses

    @staticmethod
    def _valid_address(address: str) -> bool:
        if address.count("@") != 1 or any(char.isspace() or ord(char) < 32 for char in address):
            return False
        local, domain = address.split("@", 1)
        return bool(local and domain and not domain.startswith(".") and not domain.endswith("."))

    @staticmethod
    def _unique_recipient_fields(
        to: list[str],
        cc: list[str],
        bcc: list[str],
    ) -> tuple[list[str], list[str], list[str]]:
        seen: set[str] = set()
        fields = []
        for addresses in (to, cc, bcc):
            unique = []
            for address in addresses:
                normalized = address.casefold()
                if normalized not in seen:
                    unique.append(address)
                    seen.add(normalized)
            fields.append(unique)
        return fields[0], fields[1], fields[2]

    @staticmethod
    def _unique_addresses(addresses: Iterable[str], excluded: set[str]) -> list[str]:
        result: list[str] = []
        seen = {address.casefold() for address in excluded}
        for address in addresses:
            original = address.strip()
            normalized = original.casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(original)
        return result

    @classmethod
    def _read_attachments(
        cls,
        attachments: Optional[List[Path]],
    ) -> list[PreparedAttachment]:
        snapshots = []
        for item in attachments or []:
            try:
                path = Path(item).expanduser().resolve()
                if not path.is_file():
                    raise OSError("not a regular file")
                if "\r" in path.name or "\n" in path.name:
                    raise InvalidArgumentError("Attachment filename contains a line break")
                content = path.read_bytes()
            except InvalidArgumentError:
                raise
            except (OSError, TypeError, ValueError) as exc:
                raise InvalidArgumentError(
                    f"Attachment is not a readable file: {item}"
                ) from exc
            snapshots.append(PreparedAttachment(path, path.name, content))
        return snapshots

    def _build_reply_text(self, original_email: Email, reply_body: str) -> str:
        if not isinstance(reply_body, str):
            raise InvalidArgumentError("Email body must be text")
        result = reply_body + "\n\n" + "-" * 30 + "\n"
        if self.signature:
            result += self.signature + "\n\n"
        result += "-----原始邮件-----\n"
        if original_email.date == datetime.min:
            date_str = "日期不详"
        else:
            date_str = original_email.date.strftime("%Y年%m月%d日 %A %H:%M")
        result += f"发件人: {original_email.from_}\n日期: {date_str}\n收件人: {original_email.to}"
        if original_email.cc:
            result += f"\n抄送: {original_email.cc}"
        result += f"\n主题: {original_email.subject}"
        if original_email.body:
            result += f"\n\n{original_email.body}"
        return result
