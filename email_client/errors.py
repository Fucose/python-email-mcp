"""Stable errors shared by the CLI, email clients, and MCP server."""

from __future__ import annotations

from typing import Iterable


class EmailClientError(Exception):
    """Base error with a stable machine-readable code."""

    code = "operation_failed"


class ConfigurationError(EmailClientError):
    """Raised when the external email configuration is incomplete."""

    code = "not_configured"

    def __init__(self, missing_fields: Iterable[str]):
        self.missing_fields = tuple(missing_fields)
        fields = ", ".join(self.missing_fields)
        super().__init__(f"Email configuration is incomplete: {fields}")


class AuthenticationError(EmailClientError):
    """Raised when IMAP or SMTP rejects the configured credentials."""

    code = "authentication_failed"


class TransportError(EmailClientError):
    """Raised for network or server protocol failures."""

    code = "connection_failed"


class NotFoundError(EmailClientError):
    """Raised when an email or attachment cannot be found."""

    code = "not_found"


class InvalidArgumentError(EmailClientError):
    """Raised when a caller supplies an invalid argument."""

    code = "invalid_argument"
