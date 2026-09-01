"""IMAP客户端模块"""

import imaplib
import email
import logging
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import AuthenticationError, NotFoundError, TransportError
from .models import Email, Attachment

LOGGER = logging.getLogger(__name__)


class IMAPClient:
    """IMAP客户端"""

    def __init__(self, host: str, port: int, user: str, password: str, ssl: bool = True):
        """
        初始化IMAP客户端

        Args:
            host: IMAP服务器地址
            port: IMAP端口
            user: 邮箱账号
            password: 密码或授权码
            ssl: 是否使用SSL
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self.client: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> bool:
        """
        连接到IMAP服务器

        Returns:
            bool: 是否成功连接
        """
        try:
            client_class = imaplib.IMAP4_SSL if self.ssl else imaplib.IMAP4
            self.client = client_class(self.host, self.port)
        except (OSError, imaplib.IMAP4.error) as exc:
            self.client = None
            raise TransportError(f"Unable to connect to IMAP server: {exc}") from exc

        try:
            self.client.login(self.user, self.password)
        except imaplib.IMAP4.error as exc:
            self.disconnect()
            raise AuthenticationError("IMAP authentication failed") from exc

        try:
            status, _ = self.client.select('INBOX')
            if status != 'OK':
                raise TransportError("IMAP server did not select INBOX")
        except Exception:
            self.disconnect()
            raise
        return True

    def disconnect(self):
        """断开IMAP连接"""
        if self.client:
            try:
                if getattr(self.client, "state", None) == "SELECTED":
                    self.client.close()
            except Exception:
                pass
            try:
                self.client.logout()
            except Exception:
                pass
            self.client = None

    def get_recent_emails(self, days: int = 3, limit: int = 20) -> List[Email]:
        """
        获取最近的邮件列表

        Args:
            days: 最近几天
            limit: 最大返回数量

        Returns:
            List[Email]: 邮件列表
        """
        if not self.client:
            self.connect()

        try:
            # 计算日期范围
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

            # 使用 UID 搜索邮件（获取真实 UID）
            status, messages = self.client.uid('SEARCH', None, f'(SINCE {since_date})')
            if status != 'OK':
                raise TransportError("IMAP search failed")

            email_uids = messages[0].split()

            # 获取最近的邮件（从最后开始）
            recent_uids = email_uids[-limit:] if len(email_uids) > limit else email_uids

            emails = []
            for email_uid in reversed(recent_uids):
                email_obj = self._fetch_email_by_uid(email_uid)
                if email_obj:
                    emails.append(email_obj)

            return emails

        except (AuthenticationError, TransportError):
            raise
        except Exception as exc:
            raise TransportError(f"Unable to list email: {exc}") from exc

    def search_by_subject(self, keyword: str, days: int = 7) -> List[Email]:
        """
        按主题搜索邮件

        Args:
            keyword: 主题关键词
            days: 搜索最近几天

        Returns:
            List[Email]: 匹配的邮件列表
        """
        if not self.client:
            self.connect()

        try:
            # 计算日期范围
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

            # 使用 UID 搜索邮件
            escaped_keyword = keyword.replace('\\', '\\\\').replace('"', '\\"')
            status, messages = self.client.uid(
                'SEARCH', None, f'(SUBJECT "{escaped_keyword}" SINCE {since_date})'
            )
            if status != 'OK':
                raise TransportError("IMAP subject search failed")

            email_uids = messages[0].split()

            emails = []
            for email_uid in reversed(email_uids):
                email_obj = self._fetch_email_by_uid(email_uid)
                if email_obj:
                    emails.append(email_obj)

            return emails

        except (AuthenticationError, TransportError):
            raise
        except Exception as exc:
            raise TransportError(f"Unable to search email: {exc}") from exc

    def get_email_content(self, uid: str) -> Optional[Email]:
        """
        获取邮件详细内容

        Args:
            uid: 邮件UID

        Returns:
            Optional[Email]: 邮件对象，失败返回None
        """
        if not self.client:
            self.connect()

        try:
            return self._fetch_email_by_uid(uid, full=True)
        except (AuthenticationError, TransportError):
            raise
        except Exception as exc:
            raise TransportError(f"Unable to read email: {exc}") from exc

    def download_attachments(self, uid: str, folder: Path) -> List[Path]:
        """
        下载邮件的附件

        Args:
            uid: 邮件UID
            folder: 下载文件夹

        Returns:
            List[Path]: 下载的文件路径列表
        """
        if not self.client:
            self.connect()

        # 创建下载文件夹
        folder.mkdir(parents=True, exist_ok=True)

        try:
            # 使用 UID 获取邮件
            status, msg_data = self.client.uid('FETCH', uid, '(RFC822)')
            if status != 'OK':
                raise NotFoundError(f"Email UID {uid} was not found")

            # 解析邮件
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            downloaded_files = []

            # 遍历邮件的所有部分
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                if part.get('Content-Disposition') is None:
                    continue

                filename = part.get_filename()

                if filename:
                    # 解码文件名
                    filename = Path(self._decode_str(filename).replace('\\', '/')).name
                    if not filename:
                        filename = "attachment"

                    # 保存附件
                    file_path = folder / filename

                    # 如果文件已存在，添加序号
                    counter = 1
                    original_name = file_path
                    while file_path.exists():
                        name, ext = original_name.stem, original_name.suffix
                        file_path = folder / f"{name}_{counter}{ext}"
                        counter += 1

                    # 保存文件
                    with file_path.open('wb') as f:
                        f.write(part.get_payload(decode=True))

                    downloaded_files.append(file_path)

            return downloaded_files

        except (AuthenticationError, NotFoundError, TransportError):
            raise
        except Exception as exc:
            raise TransportError(f"Unable to download attachments: {exc}") from exc

    def batch_download_attachments(self, uids: List[str], folder: Path) -> List[Path]:
        """
        批量下载多个邮件的附件

        Args:
            uids: 邮件UID列表
            folder: 下载文件夹

        Returns:
            List[Path]: 所有下载的文件路径列表
        """
        all_files = []

        for uid in uids:
            files = self.download_attachments(uid, folder)
            all_files.extend(files)

        return all_files

    def _fetch_email_by_uid(self, email_uid: bytes, full: bool = False) -> Optional[Email]:
        """
        根据UID获取邮件

        Args:
            email_uid: 邮件UID（bytes类型）
            full: 是否获取完整内容（包括正文和附件）

        Returns:
            Optional[Email]: 邮件对象
        """
        try:
            if full:
                # 使用 UID 获取完整邮件
                status, msg_data = self.client.uid('FETCH', email_uid, '(RFC822)')
            else:
                # 使用 UID 只获取头部信息
                status, msg_data = self.client.uid('FETCH', email_uid, '(BODY.PEEK[HEADER])')

            if status != 'OK':
                return None

            # 解析邮件
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # 提取基本信息
            subject = self._decode_str(msg.get('Subject', ''))
            from_ = self._decode_str(msg.get('From', ''))
            to = self._decode_str(msg.get('To', ''))
            cc = self._decode_str(msg.get('Cc', ''))
            date_str = msg.get('Date', '')

            # 解析日期
            try:
                date_tuple = email.utils.parsedate_tz(date_str)
                if date_tuple:
                    date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                else:
                    date = datetime.now()
            except Exception:
                date = datetime.now()

            # 创建邮件对象，使用真实的 IMAP UID
            email_obj = Email(
                uid=email_uid.decode() if isinstance(email_uid, bytes) else str(email_uid),
                subject=subject,
                from_=from_,
                to=to,
                cc=cc if cc else None,
                date=date
            )

            # 如果需要完整内容，提取正文和附件
            if full:
                self._extract_body_and_attachments(msg, email_obj)

            return email_obj

        except Exception as exc:
            LOGGER.warning("Unable to parse email UID %s: %s", email_uid, exc)
            return None

    def _extract_body_and_attachments(self, msg, email_obj: Email):
        """
        提取邮件正文和附件

        Args:
            msg: 邮件消息对象
            email_obj: 邮件对象（会被修改）
        """
        attachments = []

        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # 处理附件
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    filename = self._decode_str(filename)
                    size = len(part.get_payload(decode=True) or b'')

                    attachments.append(Attachment(
                        filename=filename,
                        size=size,
                        content_type=content_type,
                        uid=email_obj.uid
                    ))
                continue

            # 处理正文
            if content_type == "text/plain" and not email_obj.body:
                try:
                    # 获取负载
                    payload = part.get_payload(decode=True)
                    if not payload:
                        # 如果解码失败，尝试直接获取原始负载
                        payload = part.get_payload()

                    # 处理不同类型的负载
                    if isinstance(payload, bytes):
                        email_obj.body = self._decode_payload(payload, part)
                    elif isinstance(payload, str):
                        email_obj.body = payload
                    elif isinstance(payload, list) and len(payload) > 0:
                        # 处理 multipart 的情况
                        for subpart in payload:
                            if isinstance(subpart, str):
                                email_obj.body = subpart
                                break
                except Exception as exc:
                    LOGGER.debug("Unable to decode text/plain email part: %s", exc)

            elif content_type == "text/html" and not email_obj.html_body:
                try:
                    # 获取负载
                    payload = part.get_payload(decode=True)
                    if not payload:
                        payload = part.get_payload()

                    # 处理不同类型的负载
                    if isinstance(payload, bytes):
                        email_obj.html_body = self._decode_payload(payload, part)
                    elif isinstance(payload, str):
                        email_obj.html_body = payload
                    elif isinstance(payload, list) and len(payload) > 0:
                        for subpart in payload:
                            if isinstance(subpart, str):
                                email_obj.html_body = subpart
                                break
                except Exception as exc:
                    LOGGER.debug("Unable to decode text/html email part: %s", exc)

        email_obj.attachments = attachments

    @staticmethod
    def _decode_str(header_value: str) -> str:
        """
        解码邮件头部字符串

        Args:
            header_value: 头部值

        Returns:
            str: 解码后的字符串
        """
        if not header_value:
            return ''

        decoded_list = decode_header(header_value)
        result = ''

        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                result += content.decode(encoding if encoding else 'utf-8', errors='ignore')
            else:
                result += content

        return result

    @staticmethod
    def _decode_payload(payload: bytes, part) -> str:
        """
        解码邮件正文内容

        Args:
            payload: 邮件正文字节内容
            part: 邮件部分对象

        Returns:
            str: 解码后的字符串
        """
        # 获取字符集
        charset = part.get_content_charset() or 'utf-8'

        # 常见的中文编码列表（按优先级）
        charsets = [charset, 'utf-8', 'gbk', 'gb2312', 'gb18030', 'iso-8859-1']

        for cs in charsets:
            try:
                return payload.decode(cs, errors='strict')
            except (UnicodeDecodeError, LookupError):
                continue

        # 如果所有编码都失败，使用 replace 模式
        return payload.decode(charset, errors='replace')
