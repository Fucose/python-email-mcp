"""配置管理模块"""

import os
from pathlib import Path
from typing import Optional, Tuple


class Config:
    """配置管理类"""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置

        Args:
            config_dir: 配置文件所在目录，默认为当前目录
        """
        if config_dir is None:
            # 默认使用main.py所在目录
            config_dir = Path(__file__).parent.parent
        self.config_dir = Path(config_dir)
        self.env_file = self.config_dir / '.env'
        self.signature_file = self.config_dir / 'signature.txt'

        # 配置项
        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.imap_host: Optional[str] = None
        self.imap_port: Optional[int] = None
        self.imap_ssl: Optional[bool] = None
        self.smtp_host: Optional[str] = None
        self.smtp_port: Optional[int] = None
        self.smtp_ssl: Optional[bool] = None
        self.signature: Optional[str] = None

    def load_config(self) -> bool:
        """
        从环境变量和.env文件加载配置
        优先使用环境变量，环境变量未设置时才从.env文件读取

        Returns:
            bool: 是否成功加载
        """
        # 辅助函数：从环境变量或字符串值获取配置
        def get_config(key, parser=None):
            env_value = os.getenv(key)
            if env_value is not None:
                return parser(env_value) if parser else env_value
            return None

        # 优先从环境变量读取
        self.email = get_config('EMAIL_USER')
        self.password = get_config('EMAIL_PASSWORD')
        self.imap_host = get_config('EMAIL_IMAP_HOST')
        self.imap_port = get_config('EMAIL_IMAP_PORT', self._parse_int)
        self.imap_ssl = get_config('EMAIL_IMAP_SSL', self._parse_bool)
        self.smtp_host = get_config('EMAIL_SMTP_HOST')
        self.smtp_port = get_config('EMAIL_SMTP_PORT', self._parse_int)
        self.smtp_ssl = get_config('EMAIL_SMTP_SSL', self._parse_bool)
        signature_file_path = get_config('EMAIL_SIGNATURE_FILE')
        if signature_file_path:
            self.signature_file = Path(signature_file_path)

        # 如果环境变量未完整设置，则从.env文件读取
        if not self.email or not self.password:
            if not self.env_file.exists():
                return False

            try:
                # 直接读取并解析.env文件
                with self.env_file.open('r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 跳过注释和空行
                        if not line or line.startswith('#'):
                            continue

                        # 解析 key=value
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()

                            # 只设置未通过环境变量设置的配置
                            if key == 'EMAIL_USER' and not self.email:
                                self.email = value
                            elif key == 'EMAIL_PASSWORD' and not self.password:
                                self.password = value
                            elif key == 'EMAIL_IMAP_HOST' and not self.imap_host:
                                self.imap_host = value
                            elif key == 'EMAIL_IMAP_PORT' and not self.imap_port:
                                self.imap_port = self._parse_int(value)
                            elif key == 'EMAIL_IMAP_SSL' and self.imap_ssl is None:
                                self.imap_ssl = self._parse_bool(value)
                            elif key == 'EMAIL_SMTP_HOST' and not self.smtp_host:
                                self.smtp_host = value
                            elif key == 'EMAIL_SMTP_PORT' and not self.smtp_port:
                                self.smtp_port = self._parse_int(value)
                            elif key == 'EMAIL_SMTP_SSL' and self.smtp_ssl is None:
                                self.smtp_ssl = self._parse_bool(value)
                            elif key == 'EMAIL_SIGNATURE_FILE' and not signature_file_path:
                                self.signature_file = Path(value)

                return True
            except Exception as e:
                print(f"⚠️ 读取配置文件失败: {e}")
                return False

        return bool(self.email and self.password)

    def load_signature(self) -> str:
        """
        从signature.txt加载签名

        Returns:
            str: 签名内容，如果文件不存在则返回空字符串
        """
        if not self.signature_file.exists():
            return ''

        try:
            return self.signature_file.read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"⚠️ 读取签名文件失败: {e}")
            return ''

    def save_config(self, email: str, password: str, imap_host: str, imap_port: int, imap_ssl: bool,
                   smtp_host: str, smtp_port: int, smtp_ssl: bool) -> bool:
        """
        保存配置到.env文件

        Args:
            email: 邮箱地址
            password: 密码或授权码
            imap_host: IMAP服务器地址
            imap_port: IMAP端口
            imap_ssl: IMAP是否使用SSL
            smtp_host: SMTP服务器地址
            smtp_port: SMTP端口
            smtp_ssl: SMTP是否使用SSL

        Returns:
            bool: 是否成功保存
        """
        try:
            lines = [
                "# 邮箱账号",
                f"EMAIL_USER={email}",
                f"EMAIL_PASSWORD={password}",
                "",
                "# IMAP配置",
                f"EMAIL_IMAP_HOST={imap_host}",
                f"EMAIL_IMAP_PORT={imap_port}",
                f"EMAIL_IMAP_SSL={'true' if imap_ssl else 'false'}",
                "",
                "# SMTP配置",
                f"EMAIL_SMTP_HOST={smtp_host}",
                f"EMAIL_SMTP_PORT={smtp_port}",
                f"EMAIL_SMTP_SSL={'true' if smtp_ssl else 'false'}",
                "",
                "# 邮件签名文件（可选）",
                f"EMAIL_SIGNATURE_FILE=signature.txt"
            ]

            self.env_file.write_text('\n'.join(lines), encoding='utf-8')
            return True
        except Exception as e:
            print(f"✗ 保存配置失败: {e}")
            return False

    def get_imap_config(self) -> Tuple[str, int, str, str, bool]:
        """
        获取IMAP连接配置

        Returns:
            Tuple[str, int, str, str, bool]: (host, port, user, password, ssl)

        Raises:
            ValueError: 配置不完整时抛出异常
        """
        if not self.email or not self.password:
            raise ValueError("邮箱账号或密码未配置")

        if not self.imap_host or not self.imap_port:
            raise ValueError("IMAP配置未完整，请设置EMAIL_IMAP_HOST和EMAIL_IMAP_PORT")

        if self.imap_ssl is None:
            raise ValueError("IMAP SSL配置未设置，请设置EMAIL_IMAP_SSL")

        return self.imap_host, self.imap_port, self.email, self.password, self.imap_ssl

    def get_smtp_config(self) -> Tuple[str, int, str, str, bool]:
        """
        获取SMTP连接配置

        Returns:
            Tuple[str, int, str, str, bool]: (host, port, user, password, ssl)

        Raises:
            ValueError: 配置不完整时抛出异常
        """
        if not self.email or not self.password:
            raise ValueError("邮箱账号或密码未配置")

        if not self.smtp_host or not self.smtp_port:
            raise ValueError("SMTP配置未完整，请设置EMAIL_SMTP_HOST和EMAIL_SMTP_PORT")

        if self.smtp_ssl is None:
            raise ValueError("SMTP SSL配置未设置，请设置EMAIL_SMTP_SSL")

        return self.smtp_host, self.smtp_port, self.email, self.password, self.smtp_ssl

    def is_configured(self) -> bool:
        """
        检查配置是否完整

        Returns:
            bool: 配置是否完整
        """
        return bool(self.email and self.password)

    @staticmethod
    def _parse_int(value: Optional[str]) -> Optional[int]:
        """安全地解析整数字符串"""
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_bool(value: Optional[str]) -> Optional[bool]:
        """安全地解析布尔字符串"""
        if value is None:
            return None
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True
        if value.lower() in ('false', '0', 'no', 'off'):
            return False
        return None
