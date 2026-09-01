"""Email Client - Python邮件客户端库"""

from .client import EmailClient
from .config import Config, get_default_config_dir, get_default_download_dir
from .errors import (
    AuthenticationError,
    ConfigurationError,
    EmailClientError,
    InvalidArgumentError,
    NotFoundError,
    TransportError,
)
from .models import Email, Attachment, EmailSearchParams

__all__ = [
    "Attachment",
    "AuthenticationError",
    "Config",
    "ConfigurationError",
    "Email",
    "EmailClient",
    "EmailClientError",
    "EmailSearchParams",
    "InvalidArgumentError",
    "NotFoundError",
    "TransportError",
    "get_default_config_dir",
    "get_default_download_dir",
]
__version__ = "0.1.0"
