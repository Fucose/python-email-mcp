"""SMTP客户端模块"""

import smtplib
import logging
from email.utils import getaddresses, parseaddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import List, Optional

from .models import Email
from .errors import AuthenticationError, InvalidArgumentError, TransportError

LOGGER = logging.getLogger(__name__)


class SMTPClient:
    """SMTP客户端"""

    def __init__(self, host: str, port: int, user: str, password: str, ssl: bool = True):
        """
        初始化SMTP客户端

        Args:
            host: SMTP服务器地址
            port: SMTP端口
            user: 邮箱账号
            password: 密码或授权码
            ssl: 是否使用SSL
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self.client: Optional[smtplib.SMTP] = None
        self.signature: Optional[str] = None

    def connect(self) -> bool:
        """
        连接到SMTP服务器

        Returns:
            bool: 是否成功连接
        """
        try:
            if self.ssl:
                self.client = smtplib.SMTP_SSL(self.host, self.port)
            else:
                self.client = smtplib.SMTP(self.host, self.port)
                self.client.starttls()
        except (OSError, smtplib.SMTPException) as exc:
            self.client = None
            raise TransportError(f"Unable to connect to SMTP server: {exc}") from exc

        try:
            self.client.login(self.user, self.password)
        except smtplib.SMTPAuthenticationError as exc:
            self.disconnect()
            raise AuthenticationError("SMTP authentication failed") from exc
        except smtplib.SMTPException as exc:
            self.disconnect()
            raise TransportError(f"SMTP login failed: {exc}") from exc
        return True

    def disconnect(self):
        """断开SMTP连接"""
        if self.client:
            try:
                self.client.quit()
            except Exception:
                pass
            self.client = None

    def set_signature(self, signature: str):
        """
        设置邮件签名

        Args:
            signature: 签名内容
        """
        self.signature = signature

    def load_signature_from_file(self, signature_file: Path) -> bool:
        """
        从文件加载签名

        Args:
            signature_file: 签名文件路径

        Returns:
            bool: 是否成功加载
        """
        try:
            if signature_file.exists():
                self.signature = signature_file.read_text(encoding='utf-8').strip()
                return True
            return False
        except OSError as exc:
            LOGGER.warning("Unable to load signature file: %s", exc)
            return False

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        skip_signature: bool = False
    ) -> bool:
        """
        发送邮件

        Args:
            to: 收件人列表
            subject: 邮件主题
            body: 邮件正文
            attachments: 附件文件路径列表
            cc: 抄送列表
            bcc: 密送列表
            skip_signature: 是否跳过添加签名（用于回复邮件）

        Returns:
            bool: 是否成功发送
        """
        if not self.client:
            self.connect()

        try:
            # 添加签名到正文（除非跳过）
            if self.signature and not skip_signature:
                body = body + '\n\n' + self.signature

            # 创建邮件对象
            if attachments:
                msg = MIMEMultipart()
                msg.attach(MIMEText(body, 'plain', 'utf-8'))
            else:
                msg = MIMEText(body, 'plain', 'utf-8')

            # 设置邮件头
            msg['From'] = self.user
            msg['To'] = ', '.join(to)
            msg['Subject'] = subject

            if cc:
                msg['Cc'] = ', '.join(cc)

            # 添加附件
            if attachments:
                for attachment_path in attachments:
                    if not self._add_attachment(msg, attachment_path):
                        raise InvalidArgumentError(f"Attachment is not a readable file: {attachment_path}")

            # 发送邮件
            all_recipients = to.copy()
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)

            self.client.send_message(msg, to_addrs=all_recipients)
            return True

        except (AuthenticationError, InvalidArgumentError, TransportError):
            raise
        except smtplib.SMTPAuthenticationError as exc:
            raise AuthenticationError("SMTP authentication failed") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise TransportError(f"Unable to send email: {exc}") from exc

    def reply_email(
        self,
        original_email: Email,
        body: str,
        attachments: Optional[List[Path]] = None,
        reply_all: bool = False
    ) -> bool:
        """
        回复邮件

        Args:
            original_email: 原始邮件对象
            body: 回复正文
            attachments: 附件文件路径列表
            reply_all: 是否回复全部

        Returns:
            bool: 是否成功发送
        """
        # 构建回复正文（包含签名和引用原文）
        reply_body = self._build_reply_text(original_email, body)

        # 确定收件人
        sender = parseaddr(original_email.from_)[1]
        to = [sender] if sender else []
        cc = None

        if reply_all:
            own_address = parseaddr(self.user)[1].lower()
            to_candidates = [sender, *(address for _, address in getaddresses([original_email.to]))]
            to = self._unique_addresses(to_candidates, excluded={own_address})
            cc_candidates = (
                [address for _, address in getaddresses([original_email.cc])]
                if original_email.cc
                else []
            )
            cc = self._unique_addresses(
                cc_candidates,
                excluded={own_address, *(address.lower() for address in to)},
            ) or None

        # 构建主题（添加Re:前缀）
        subject = original_email.subject
        if not subject.upper().startswith('RE:'):
            subject = f'Re: {subject}'

        # 发送回复邮件（跳过自动添加签名，因为已经在 _build_reply_text 中处理）
        return self.send_email(
            to=to,
            subject=subject,
            body=reply_body,
            attachments=attachments,
            cc=cc,
            skip_signature=True
        )

    def _add_attachment(self, msg: MIMEMultipart, file_path: Path) -> bool:
        """
        添加附件到邮件

        Args:
            msg: 邮件对象
            file_path: 文件路径

        Returns:
            bool: 是否成功添加
        """
        try:
            # 验证文件存在
            if not file_path.exists() or not file_path.is_file():
                return False

            # 读取文件内容
            with file_path.open('rb') as f:
                content = f.read()

            # 创建附件部分
            part = MIMEApplication(content)
            part.add_header('Content-Disposition', 'attachment', filename=file_path.name)
            msg.attach(part)

            return True

        except OSError as exc:
            LOGGER.warning("Unable to read attachment %s: %s", file_path, exc)
            return False

    def _build_reply_text(self, original_email: Email, reply_body: str) -> str:
        """
        构建回复文本（包含签名和引用原文）

        Args:
            original_email: 原始邮件对象
            reply_body: 回复正文

        Returns:
            str: 完整的回复文本
        """
        # 回复正文 + 横线 + 签名
        result = reply_body + '\n\n' + '-' * 30 + '\n'

        # 添加签名
        if self.signature:
            result += self.signature + '\n\n'

        # 添加引用原文标记
        result += '-----原始邮件-----\n'

        # 格式化日期
        date_str = original_email.date.strftime('%Y年%m月%d日 %A %H:%M')

        # 构建引用文本
        result += f"""发件人: {original_email.from_}
日期: {date_str}
收件人: {original_email.to}"""

        if original_email.cc:
            result += f"\n抄送: {original_email.cc}"

        result += f"\n主题: {original_email.subject}"

        # 添加原文内容
        if original_email.body:
            result += f"\n\n{original_email.body}"

        return result

    @staticmethod
    def _extract_email(email_str: str) -> str:
        """
        从邮件地址字符串中提取纯邮箱地址

        Args:
            email_str: 邮件地址字符串（可能包含名称）

        Returns:
            str: 纯邮箱地址
        """
        if not email_str:
            return ''

        # 简单提取：寻找<...>中的内容
        start = email_str.find('<')
        end = email_str.find('>')

        if start != -1 and end != -1 and end > start:
            return email_str[start + 1:end].strip()

        # 如果没有<...>，直接返回
        return email_str.strip()

    @staticmethod
    def _unique_addresses(addresses: List[str], excluded: set[str]) -> List[str]:
        result = []
        seen = set(excluded)
        for address in addresses:
            normalized = address.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(address.strip())
        return result
