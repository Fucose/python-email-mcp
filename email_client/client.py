"""核心邮件客户端"""

from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config
from .imap_client import IMAPClient
from .smtp_client import SMTPClient
from .models import Email


class EmailClient:
    """邮件客户端（整合IMAP和SMTP）"""

    def __init__(self, config: Optional[Config] = None):
        """
        初始化邮件客户端

        Args:
            config: 配置对象，如果为None则自动创建
        """
        self.config = config or Config()
        self.config.load_config()

        self.imap_client: Optional[IMAPClient] = None
        self.smtp_client: Optional[SMTPClient] = None

    def test_connection(self, test_type: str = 'both') -> dict:
        """
        测试IMAP/SMTP连接

        Args:
            test_type: 测试类型 ("imap", "smtp", "both")

        Returns:
            dict: 测试结果
        """
        results = {}

        if test_type in ('imap', 'both'):
            try:
                host, port, user, password, ssl = self.config.get_imap_config()
                imap = IMAPClient(host, port, user, password, ssl)
                if imap.connect():
                    imap.disconnect()
                    results['imap'] = '✅ IMAP服务器连接测试成功！'
                else:
                    results['imap'] = '✗ IMAP连接测试失败'
            except Exception as e:
                results['imap'] = f'✗ IMAP连接测试失败: {e}'

        if test_type in ('smtp', 'both'):
            try:
                host, port, user, password, ssl = self.config.get_smtp_config()
                smtp = SMTPClient(host, port, user, password, ssl)
                if smtp.connect():
                    smtp.disconnect()
                    results['smtp'] = '✅ SMTP服务器连接测试成功！'
                else:
                    results['smtp'] = '✗ SMTP连接测试失败'
            except Exception as e:
                results['smtp'] = f'✗ SMTP连接测试失败: {e}'

        return results

    def get_recent_emails(self, days: int = 3, limit: int = 20) -> List[Email]:
        """
        获取最近的邮件列表

        Args:
            days: 最近几天
            limit: 最大返回数量

        Returns:
            List[Email]: 邮件列表
        """
        if not self.imap_client:
            self._init_imap_client()

        if self.imap_client:
            return self.imap_client.get_recent_emails(days, limit)

        return []

    def search_emails(self, subject: str, days: int = 7) -> List[Email]:
        """
        按主题搜索邮件

        Args:
            subject: 主题关键词
            days: 搜索最近几天

        Returns:
            List[Email]: 匹配的邮件列表
        """
        if not self.imap_client:
            self._init_imap_client()

        if self.imap_client:
            return self.imap_client.search_by_subject(subject, days)

        return []

    def get_email(self, uid: str) -> Optional[Email]:
        """
        获取邮件详细内容

        Args:
            uid: 邮件UID

        Returns:
            Optional[Email]: 邮件对象
        """
        if not self.imap_client:
            self._init_imap_client()

        if self.imap_client:
            return self.imap_client.get_email_content(uid)

        return None

    def download_attachments(self, uid: str, folder: Path = Path('downloads')) -> List[Path]:
        """
        下载邮件附件

        Args:
            uid: 邮件UID
            folder: 下载文件夹

        Returns:
            List[Path]: 下载的文件路径列表
        """
        if not self.imap_client:
            self._init_imap_client()

        if self.imap_client:
            return self.imap_client.download_attachments(uid, folder)

        return []

    def batch_download_attachments(
        self,
        subject: str,
        days: int = 7,
        folder: Path = Path('downloads')
    ) -> List[Path]:
        """
        批量下载附件（基于搜索结果）

        Args:
            subject: 搜索主题
            days: 搜索最近几天
            folder: 下载文件夹

        Returns:
            List[Path]: 所有下载的文件路径列表
        """
        # 先搜索邮件
        emails = self.search_emails(subject, days)

        # 获取所有邮件的UID
        uids = [email.uid for email in emails]

        # 批量下载
        if not self.imap_client:
            self._init_imap_client()

        if self.imap_client:
            return self.imap_client.batch_download_attachments(uids, folder)

        return []

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
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

        Returns:
            bool: 是否成功发送
        """
        if not self.smtp_client:
            self._init_smtp_client()

        if self.smtp_client:
            return self.smtp_client.send_email(to, subject, body, attachments, cc, bcc)

        return False

    def reply(
        self,
        uid: str,
        body: str,
        attachments: Optional[List[Path]] = None,
        reply_all: bool = False
    ) -> bool:
        """
        回复邮件

        Args:
            uid: 原邮件UID
            body: 回复正文
            attachments: 附件文件路径列表
            reply_all: 是否回复全部

        Returns:
            bool: 是否成功发送
        """
        # 获取原邮件
        original_email = self.get_email(uid)
        if not original_email:
            print("✗ 未找到原邮件")
            return False

        if not self.smtp_client:
            self._init_smtp_client()

        if self.smtp_client:
            return self.smtp_client.reply_email(original_email, body, attachments, reply_all)

        return False

    def disconnect(self):
        """断开所有连接"""
        if self.imap_client:
            self.imap_client.disconnect()
        if self.smtp_client:
            self.smtp_client.disconnect()

    def _init_imap_client(self):
        """初始化IMAP客户端"""
        try:
            host, port, user, password, ssl = self.config.get_imap_config()
            self.imap_client = IMAPClient(host, port, user, password, ssl)
            self.imap_client.connect()
        except Exception as e:
            print(f"✗ 初始化IMAP客户端失败: {e}")
            self.imap_client = None

    def _init_smtp_client(self):
        """初始化SMTP客户端"""
        try:
            host, port, user, password, ssl = self.config.get_smtp_config()
            self.smtp_client = SMTPClient(host, port, user, password, ssl)
            self.smtp_client.connect()

            # 加载签名
            signature = self.config.load_signature()
            if signature:
                self.smtp_client.set_signature(signature)
        except Exception as e:
            print(f"✗ 初始化SMTP客户端失败: {e}")
            self.smtp_client = None
