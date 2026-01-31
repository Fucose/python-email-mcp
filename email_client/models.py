"""数据模型定义"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Attachment:
    """邮件附件"""
    filename: str
    size: int
    content_type: str
    uid: Optional[str] = None  # 邮件UID，用于下载


@dataclass
class Email:
    """邮件对象"""
    uid: str
    subject: str
    from_: str  # 发件人
    to: str  # 收件人
    date: datetime
    body: Optional[str] = None
    html_body: Optional[str] = None
    cc: Optional[str] = None
    attachments: List[Attachment] = field(default_factory=list)

    def __repr__(self):
        return f"Email(uid={self.uid}, subject='{self.subject}', from='{self.from_}')"


@dataclass
class EmailSearchParams:
    """邮件搜索参数"""
    subject: Optional[str] = None
    from_: Optional[str] = None
    days: int = 7
    limit: int = 20
