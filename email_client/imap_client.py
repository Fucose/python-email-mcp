"""IMAP客户端模块"""

import imaplib
import email
import logging
import re
import ssl
from email.header import decode_header
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .errors import AuthenticationError, InvalidArgumentError, NotFoundError, TransportError
from .models import Email, Attachment

LOGGER = logging.getLogger(__name__)

_IMAP_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_MAX_UID = 4_294_967_295


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
            ssl: 是否使用隐式TLS；为False时仍要求STARTTLS
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self.client: Optional[imaplib.IMAP4] = None

    def connect(self) -> bool:
        """
        连接到IMAP服务器

        Returns:
            bool: 是否成功连接
        """
        try:
            context = ssl.create_default_context()
            if self.ssl:
                self.client = imaplib.IMAP4_SSL(
                    self.host, self.port, ssl_context=context
                )
            else:
                self.client = imaplib.IMAP4(self.host, self.port)
                self.client.starttls(ssl_context=context)

            try:
                self.client.login(self.user, self.password)
            except imaplib.IMAP4.abort as exc:
                raise TransportError(f"Unable to authenticate to IMAP server: {exc}") from exc
            except imaplib.IMAP4.error as exc:
                raise AuthenticationError("IMAP authentication failed") from exc

            status, _ = self.client.select('INBOX', readonly=True)
            if status != 'OK':
                raise TransportError("IMAP server did not select INBOX")
        except (AuthenticationError, TransportError):
            self.disconnect()
            raise
        except Exception as exc:
            self.disconnect()
            raise TransportError(f"Unable to connect to IMAP server: {exc}") from exc
        return True

    def disconnect(self):
        """断开IMAP连接"""
        if self.client:
            try:
                self.client.logout()
            except Exception:
                pass
            finally:
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
            since_date = self._format_imap_date(datetime.now() - timedelta(days=days))

            # 使用 UID 搜索邮件（获取真实 UID）
            status, messages = self.client.uid('SEARCH', None, f'(SINCE {since_date})')
            if status != 'OK':
                raise TransportError("IMAP search failed")

            email_uids = self._uids_from_search_response(messages)

            # 获取最近的邮件（从最后开始）
            recent_uids = email_uids[-limit:] if len(email_uids) > limit else email_uids

            emails = []
            for email_uid in reversed(recent_uids):
                email_obj = self._fetch_email_by_uid(email_uid)
                if email_obj:
                    emails.append(email_obj)

            return emails

        except (AuthenticationError, InvalidArgumentError, TransportError):
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
        self._validate_search_keyword(keyword)

        if not self.client:
            self.connect()

        try:
            # 计算日期范围
            since_date = self._format_imap_date(datetime.now() - timedelta(days=days))

            # IMAP literals safely carry UTF-8 search text without quoting it into
            # the command line, where quotes and command separators are ambiguous.
            self.client.literal = keyword.encode('utf-8')
            # imaplib emits its literal after every argument, so SUBJECT must
            # be the final criterion before that literal.
            search_args = ('SINCE', since_date, 'SUBJECT')
            if getattr(self.client, 'utf8_enabled', False):
                status, messages = self.client.uid('SEARCH', *search_args)
            else:
                status, messages = self.client.uid(
                    'SEARCH', 'CHARSET', 'UTF-8', *search_args
                )
            if status != 'OK':
                raise TransportError("IMAP subject search failed")

            email_uids = self._uids_from_search_response(messages)

            emails = []
            for email_uid in reversed(email_uids):
                email_obj = self._fetch_email_by_uid(email_uid)
                if email_obj:
                    emails.append(email_obj)

            return emails

        except (AuthenticationError, InvalidArgumentError, TransportError):
            raise
        except Exception as exc:
            raise TransportError(f"Unable to search email: {exc}") from exc
        finally:
            if self.client is not None and getattr(self.client, 'literal', None) is not None:
                self.client.literal = None

    def get_email_content(self, uid: str) -> Optional[Email]:
        """
        获取邮件详细内容

        Args:
            uid: 邮件UID

        Returns:
            Optional[Email]: 邮件对象，失败返回None
        """
        uid = self._validate_uid(uid)
        if not self.client:
            self.connect()

        try:
            return self._fetch_email_by_uid(uid, full=True)
        except (AuthenticationError, InvalidArgumentError, TransportError):
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
        uid = self._validate_uid(uid)
        if not self.client:
            self.connect()

        # 创建下载文件夹
        folder.mkdir(parents=True, exist_ok=True)

        try:
            # 使用 UID 获取邮件
            status, msg_data = self.client.uid('FETCH', uid, '(BODY.PEEK[])')
            if status != 'OK':
                raise TransportError(f"Unable to fetch email UID {uid}")

            # 解析邮件
            raw_email = self._fetch_payload(msg_data)
            if raw_email is None:
                raise NotFoundError(f"Email UID {uid} was not found")
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

        except (AuthenticationError, InvalidArgumentError, NotFoundError, TransportError):
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
        validated_uids = [self._validate_uid(uid) for uid in uids]
        all_files = []

        for uid in validated_uids:
            files = self.download_attachments(uid, folder)
            all_files.extend(files)

        return all_files

    def _fetch_email_by_uid(self, email_uid: str | bytes, full: bool = False) -> Optional[Email]:
        """
        根据UID获取邮件

        Args:
            email_uid: 邮件UID
            full: 是否获取完整内容（包括正文和附件）

        Returns:
            Optional[Email]: 邮件对象
        """
        email_uid = self._validate_uid(email_uid)
        if not self.client:
            raise TransportError("IMAP client is not connected")

        try:
            if full:
                # BODY.PEEK avoids setting the Seen flag while retrieving content.
                status, msg_data = self.client.uid('FETCH', email_uid, '(BODY.PEEK[])')
            else:
                status, msg_data = self.client.uid(
                    'FETCH', email_uid, '(BODY.PEEK[HEADER])'
                )
        except Exception as exc:
            raise TransportError(f"Unable to fetch email UID {email_uid}: {exc}") from exc

        if status != 'OK':
            raise TransportError(f"Unable to fetch email UID {email_uid}")

        raw_email = self._fetch_payload(msg_data)
        if raw_email is None:
            return None

        try:
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
                    parsed_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                else:
                    parsed_date = datetime.min
            except Exception:
                parsed_date = datetime.min

            # 创建邮件对象，使用真实的 IMAP UID
            email_obj = Email(
                uid=email_uid,
                subject=subject,
                from_=from_,
                to=to,
                cc=cc if cc else None,
                date=parsed_date,
                reply_to=self._optional_header(msg, 'Reply-To'),
                message_id=self._optional_header(msg, 'Message-ID'),
                references=self._optional_header(msg, 'References'),
            )

            # 如果需要完整内容，提取正文和附件
            if full:
                self._extract_body_and_attachments(msg, email_obj)

            return email_obj
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(f"Unable to parse email UID {email_uid}: {exc}") from exc

    @staticmethod
    def _validate_uid(uid, *, server_response: bool = False) -> str:
        """Return a canonical decimal UID or reject it before issuing a command."""
        error_type = TransportError if server_response else InvalidArgumentError
        if isinstance(uid, bytes):
            try:
                uid = uid.decode('ascii')
            except UnicodeDecodeError as exc:
                raise error_type("IMAP UID must contain only ASCII decimal digits") from exc
        if not isinstance(uid, str) or not uid or any(char < '0' or char > '9' for char in uid):
            raise error_type("IMAP UID must contain only ASCII decimal digits")

        normalized = uid.lstrip('0') or '0'
        if len(normalized) > 10 or int(normalized) < 1 or int(normalized) > _MAX_UID:
            raise error_type(f"IMAP UID must be between 1 and {_MAX_UID}")
        return normalized

    @staticmethod
    def _format_imap_date(value: date) -> str:
        """Format an IMAP date using protocol month names independent of locale."""
        return f"{value.day:02d}-{_IMAP_MONTHS[value.month - 1]}-{value.year:04d}"

    @staticmethod
    def _validate_search_keyword(keyword: str) -> None:
        if not isinstance(keyword, str):
            raise InvalidArgumentError("IMAP subject keyword must be text")
        if any(char in keyword for char in ('\r', '\n', '\x00')):
            raise InvalidArgumentError("IMAP subject keyword cannot contain CR, LF, or NUL")

    @staticmethod
    def _uids_from_search_response(messages) -> List[str]:
        if not messages or messages[0] is None:
            return []
        response = messages[0]
        if isinstance(response, bytes):
            uids = response.split()
        elif isinstance(response, str):
            uids = response.split()
        else:
            raise TransportError("IMAP search returned a malformed UID list")
        return [IMAPClient._validate_uid(uid, server_response=True) for uid in uids]

    @staticmethod
    def _fetch_payload(msg_data) -> Optional[bytes]:
        if not msg_data:
            return None
        for item in msg_data:
            if item is None:
                continue
            if isinstance(item, tuple) and len(item) >= 2:
                payload = item[1]
                if payload is None:
                    continue
                if isinstance(payload, bytes):
                    return payload
            raise TransportError("IMAP FETCH returned a malformed message payload")
        return None

    @classmethod
    def _optional_header(cls, msg, name: str) -> Optional[str]:
        value = msg.get(name, '')
        value = cls._decode_str(value).strip()
        return value or None

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

        # Unfold only legal header continuations. Other line breaks remain for
        # callers such as SMTP validation to reject.
        header_value = re.sub(r'\r?\n[ \t]+', ' ', header_value)
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
