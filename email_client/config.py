"""Per-user configuration management for Windows, WSL, and Linux."""

from __future__ import annotations

import logging
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Mapping, Optional, Tuple

from .errors import ConfigurationError

LOGGER = logging.getLogger(__name__)


def get_setup_command(
    python_executable: Optional[str] = None,
    main_script: Optional[str] = None,
    platform_name: Optional[str] = None,
) -> str:
    """Build a shell command that runs setup with this installation's code."""
    executable = python_executable or sys.executable
    script = main_script or str(Path(__file__).resolve().parent.parent / "main.py")
    arguments = [executable, "-X", "utf8", script, "cli", "setup"]
    platform_name = os.name if platform_name is None else platform_name

    if platform_name == "nt":
        def quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        return "& " + " ".join(quote(value) for value in arguments)
    return shlex.join(arguments)


SETUP_COMMAND = get_setup_command()

FIELD_ENV_KEYS = {
    "email": "EMAIL_USER",
    "password": "EMAIL_PASSWORD",
    "imap_host": "EMAIL_IMAP_HOST",
    "imap_port": "EMAIL_IMAP_PORT",
    "imap_ssl": "EMAIL_IMAP_SSL",
    "smtp_host": "EMAIL_SMTP_HOST",
    "smtp_port": "EMAIL_SMTP_PORT",
    "smtp_ssl": "EMAIL_SMTP_SSL",
}


def get_default_config_dir(
    *,
    environ: Optional[Mapping[str, str]] = None,
    platform_name: Optional[str] = None,
    home: Optional[Path] = None,
) -> Path:
    """Return the external per-user config directory without creating it."""
    env = os.environ if environ is None else environ
    override = env.get("EMAIL_MCP_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    platform_name = os.name if platform_name is None else platform_name
    user_home = Path.home() if home is None else Path(home)
    if platform_name == "nt":
        appdata = env.get("APPDATA", "").strip()
        base = Path(appdata).expanduser() if appdata else user_home / "AppData" / "Roaming"
    else:
        xdg_config_home = env.get("XDG_CONFIG_HOME", "").strip()
        base = Path(xdg_config_home).expanduser() if xdg_config_home else user_home / ".config"
    return base / "python-email-mcp"


def get_default_download_dir(*, home: Optional[Path] = None) -> Path:
    """Return the default attachment directory outside the plugin cache."""
    user_home = Path.home() if home is None else Path(home)
    return user_home / "Downloads" / "python-email-mcp"


class Config:
    """Load environment-over-file settings and save a restricted config file."""

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        *,
        environ: Optional[Mapping[str, str]] = None,
        platform_name: Optional[str] = None,
        home: Optional[Path] = None,
    ):
        self._environ = os.environ if environ is None else environ
        self.config_dir = Path(config_dir) if config_dir is not None else get_default_config_dir(
            environ=self._environ,
            platform_name=platform_name,
            home=home,
        )
        self.env_file = self.config_dir / "config.env"
        self.signature_file = self.config_dir / "signature.txt"

        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.imap_host: Optional[str] = None
        self.imap_port: Optional[int] = None
        self.imap_ssl: Optional[bool] = None
        self.smtp_host: Optional[str] = None
        self.smtp_port: Optional[int] = None
        self.smtp_ssl: Optional[bool] = None

    def load_config(self) -> bool:
        """Reload config from disk, then overlay non-empty environment values."""
        values: dict[str, str] = {}
        if self.env_file.exists():
            try:
                for raw_line in self.env_file.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
            except OSError as exc:
                LOGGER.error("Unable to read email configuration: %s", exc)

        for key in (*FIELD_ENV_KEYS.values(), "EMAIL_SIGNATURE_FILE"):
            env_value = self._environ.get(key)
            if env_value is not None and env_value.strip():
                values[key] = env_value.strip()

        self.email = values.get("EMAIL_USER") or None
        self.password = values.get("EMAIL_PASSWORD") or None
        self.imap_host = values.get("EMAIL_IMAP_HOST") or None
        self.imap_port = self._parse_int(values.get("EMAIL_IMAP_PORT"))
        self.imap_ssl = self._parse_bool(values.get("EMAIL_IMAP_SSL"))
        self.smtp_host = values.get("EMAIL_SMTP_HOST") or None
        self.smtp_port = self._parse_int(values.get("EMAIL_SMTP_PORT"))
        self.smtp_ssl = self._parse_bool(values.get("EMAIL_SMTP_SSL"))

        signature_value = values.get("EMAIL_SIGNATURE_FILE", "signature.txt")
        signature_path = Path(signature_value).expanduser()
        if not signature_path.is_absolute():
            signature_path = self.config_dir / signature_path
        self.signature_file = signature_path
        return self.is_configured()

    def load_signature(self) -> str:
        """Load a signature without treating a missing file as an error."""
        if not self.signature_file.exists():
            return ""
        try:
            return self.signature_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            LOGGER.warning("Unable to read email signature: %s", exc)
            return ""

    def save_config(
        self,
        email: str,
        password: str,
        imap_host: str,
        imap_port: int,
        imap_ssl: bool,
        smtp_host: str,
        smtp_port: int,
        smtp_ssl: bool,
    ) -> bool:
        """Write config outside the plugin cache with best-effort private modes."""
        serialized = {
            "EMAIL_USER": email.strip(),
            "EMAIL_PASSWORD": password,
            "EMAIL_IMAP_HOST": imap_host.strip(),
            "EMAIL_IMAP_PORT": str(imap_port),
            "EMAIL_IMAP_SSL": "true" if imap_ssl else "false",
            "EMAIL_SMTP_HOST": smtp_host.strip(),
            "EMAIL_SMTP_PORT": str(smtp_port),
            "EMAIL_SMTP_SSL": "true" if smtp_ssl else "false",
            "EMAIL_SIGNATURE_FILE": "signature.txt",
        }
        for key, value in serialized.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"{key} must not contain line breaks")

        lines = [
            "# Generated by python-email-mcp. Keep this file private.",
            *(f"{key}={value}" for key, value in serialized.items()),
            "",
        ]
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self._restrict_permissions(self.config_dir, directory=True)
            self.env_file.write_text("\n".join(lines), encoding="utf-8")
            self._restrict_permissions(self.env_file, directory=False)
            return True
        except OSError as exc:
            LOGGER.error("Unable to save email configuration: %s", exc)
            return False

    def missing_fields(self, protocol: Optional[str] = None) -> list[str]:
        """Return stable environment-key names for missing or invalid fields."""
        if protocol == "imap":
            names = ("email", "password", "imap_host", "imap_port", "imap_ssl")
        elif protocol == "smtp":
            names = ("email", "password", "smtp_host", "smtp_port", "smtp_ssl")
        else:
            names = tuple(FIELD_ENV_KEYS)
        return [FIELD_ENV_KEYS[name] for name in names if getattr(self, name) is None]

    def status(self) -> dict:
        """Return non-secret configuration metadata suitable for MCP output."""
        self.load_config()
        return {
            "configured": self.is_configured(),
            "config_file": str(self.env_file),
            "signature_file": str(self.signature_file),
            "missing_fields": self.missing_fields(),
            "setup_command": SETUP_COMMAND,
        }

    def get_imap_config(self) -> Tuple[str, int, str, str, bool]:
        missing = self.missing_fields("imap")
        if missing:
            raise ConfigurationError(missing)
        return self.imap_host, self.imap_port, self.email, self.password, self.imap_ssl

    def get_smtp_config(self) -> Tuple[str, int, str, str, bool]:
        missing = self.missing_fields("smtp")
        if missing:
            raise ConfigurationError(missing)
        return self.smtp_host, self.smtp_port, self.email, self.password, self.smtp_ssl

    def is_configured(self) -> bool:
        return not self.missing_fields()

    @staticmethod
    def _restrict_permissions(path: Path, *, directory: bool) -> None:
        mode = stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if directory else 0)
        try:
            os.chmod(path, mode)
        except OSError as exc:
            LOGGER.warning("Unable to restrict permissions for %s: %s", path, exc)

    @staticmethod
    def _parse_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if 1 <= parsed <= 65535 else None

    @staticmethod
    def _parse_bool(value: Optional[str]) -> Optional[bool]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None
