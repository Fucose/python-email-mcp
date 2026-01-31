"""Email Client - Python邮件客户端库"""

from .client import EmailClient
from .config import Config
from .models import Email, Attachment, EmailSearchParams

__all__ = ['EmailClient', 'Config', 'Email', 'Attachment', 'EmailSearchParams']
__version__ = '1.0.0'
