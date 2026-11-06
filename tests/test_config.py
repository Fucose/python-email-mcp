import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from email_client.config import (
    SETUP_COMMAND,
    Config,
    get_default_config_dir,
    get_default_download_dir,
    get_setup_command,
)


class ConfigPathTests(unittest.TestCase):
    def test_windows_uses_appdata(self):
        result = get_default_config_dir(
            environ={"APPDATA": r"C:\Users\tester\AppData\Roaming"},
            platform_name="nt",
            home=Path(r"C:\Users\tester"),
        )
        self.assertEqual(result, Path(r"C:\Users\tester\AppData\Roaming") / "python-email-mcp")

    def test_linux_uses_xdg_config_home(self):
        result = get_default_config_dir(
            environ={"XDG_CONFIG_HOME": "/tmp/custom-config"},
            platform_name="posix",
            home=Path("/home/tester"),
        )
        self.assertEqual(result, Path("/tmp/custom-config/python-email-mcp"))

    def test_linux_falls_back_to_dot_config(self):
        result = get_default_config_dir(
            environ={}, platform_name="posix", home=Path("/home/tester")
        )
        self.assertEqual(result, Path("/home/tester/.config/python-email-mcp"))

    def test_override_wins_on_every_platform(self):
        result = get_default_config_dir(
            environ={"EMAIL_MCP_CONFIG_DIR": "/tmp/email-settings"},
            platform_name="nt",
            home=Path("/unused"),
        )
        self.assertEqual(result, Path("/tmp/email-settings"))

    def test_default_download_directory_is_outside_project(self):
        self.assertEqual(
            get_default_download_dir(home=Path("/home/tester")),
            Path("/home/tester/Downloads/python-email-mcp"),
        )


class ConfigLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_dir = Path(self.temp_dir.name)

    def _write_complete_config(self):
        (self.config_dir / "config.env").write_text(
            "\n".join(
                [
                    "EMAIL_USER=file@example.com",
                    "EMAIL_PASSWORD=file-secret",
                    "EMAIL_IMAP_HOST=imap.file.example",
                    "EMAIL_IMAP_PORT=993",
                    "EMAIL_IMAP_SSL=true",
                    "EMAIL_SMTP_HOST=smtp.file.example",
                    "EMAIL_SMTP_PORT=465",
                    "EMAIL_SMTP_SSL=true",
                    "EMAIL_SIGNATURE_FILE=signatures/default.txt",
                ]
            ),
            encoding="utf-8",
        )

    def test_environment_values_override_file_values(self):
        self._write_complete_config()
        config = Config(
            self.config_dir,
            environ={"EMAIL_USER": "env@example.com", "EMAIL_IMAP_PORT": "1993"},
        )
        self.assertTrue(config.load_config())
        self.assertEqual(config.email, "env@example.com")
        self.assertEqual(config.imap_port, 1993)
        self.assertEqual(config.password, "file-secret")

    def test_relative_signature_is_resolved_against_config_directory(self):
        self._write_complete_config()
        config = Config(self.config_dir, environ={})
        config.load_config()
        self.assertEqual(
            config.signature_file,
            self.config_dir / "signatures" / "default.txt",
        )

    def test_status_never_contains_password(self):
        self._write_complete_config()
        status = Config(self.config_dir, environ={}).status()
        self.assertTrue(status["configured"])
        self.assertNotIn("password", repr(status).lower())
        self.assertNotIn("file-secret", repr(status))

    def test_missing_fields_include_invalid_port_and_boolean(self):
        (self.config_dir / "config.env").write_text(
            "EMAIL_USER=a@example.com\nEMAIL_PASSWORD=x\nEMAIL_IMAP_PORT=0\nEMAIL_IMAP_SSL=maybe\n",
            encoding="utf-8",
        )
        config = Config(self.config_dir, environ={})
        config.load_config()
        self.assertIn("EMAIL_IMAP_PORT", config.missing_fields())
        self.assertIn("EMAIL_IMAP_SSL", config.missing_fields())

    def test_save_creates_directory_and_requests_private_modes(self):
        nested = self.config_dir / "nested"
        config = Config(nested, environ={})
        with patch("email_client.config.os.chmod") as chmod:
            self.assertTrue(
                config.save_config(
                    "a@example.com", "secret", "imap.example.com", 993, True,
                    "smtp.example.com", 465, True,
                )
            )
        self.assertTrue(config.env_file.exists())
        calls = {call.args for call in chmod.call_args_list}
        self.assertIn((nested, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR), calls)
        self.assertIn((config.env_file, stat.S_IRUSR | stat.S_IWUSR), calls)

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are not meaningful on Windows")
    def test_saved_file_is_owner_read_write_only_on_posix(self):
        config = Config(self.config_dir / "posix", environ={})
        config.save_config(
            "a@example.com", "secret", "imap.example.com", 993, True,
            "smtp.example.com", 465, True,
        )
        self.assertEqual(stat.S_IMODE(config.env_file.stat().st_mode), 0o600)


class SetupCommandTests(unittest.TestCase):
    def test_status_command_uses_current_interpreter_and_bundled_main(self):
        with tempfile.TemporaryDirectory() as temporary:
            status = Config(Path(temporary), environ={}).status()

        command = status["setup_command"]
        main_script = str((Path(__file__).resolve().parent.parent / "main.py").resolve())
        self.assertEqual(command, SETUP_COMMAND)
        self.assertEqual(command, get_setup_command())
        self.assertIn(sys.executable, command)
        self.assertIn(main_script, command)
        self.assertNotIn("github.com", command)
        self.assertNotIn("--from", command)

        if os.name == "nt":
            self.assertTrue(command.startswith("& "))
        else:
            self.assertEqual(
                shlex.split(command),
                [sys.executable, main_script, "cli", "setup"],
            )

    def test_setup_command_quotes_arguments_with_spaces_and_apostrophes(self):
        executable = r"C:\Program Files\O'Brien\python.exe"
        main_script = r"C:\Plugin Folder\Owner's Files\main.py"
        powershell_command = get_setup_command(
            executable, main_script, platform_name="nt"
        )
        self.assertEqual(
            powershell_command,
            "& 'C:\\Program Files\\O''Brien\\python.exe' "
            "'C:\\Plugin Folder\\Owner''s Files\\main.py' 'cli' 'setup'",
        )

        posix_executable = "/tmp/Python O'Brien/bin/python"
        posix_script = "/tmp/Plugin Owner's Folder/main.py"
        posix_command = get_setup_command(
            posix_executable, posix_script, platform_name="posix"
        )
        self.assertEqual(
            shlex.split(posix_command),
            [posix_executable, posix_script, "cli", "setup"],
        )

    @unittest.skipIf(os.name == "nt" and not (shutil.which("pwsh") or shutil.which("powershell")),
                     "PowerShell is required to execute the generated setup command")
    def test_generated_setup_command_help_runs_from_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix="email setup command ") as temporary:
            temp_root = Path(temporary)
            cwd = temp_root / "unrelated cwd with spaces and 'quotes'"
            cwd.mkdir()
            config_dir = temp_root / "isolated config with spaces and 'quotes'"
            environment = os.environ.copy()
            for key in tuple(environment):
                if key.startswith("EMAIL_"):
                    environment.pop(key)
            environment["EMAIL_MCP_CONFIG_DIR"] = str(config_dir)

            command = get_setup_command() + " --help"
            if os.name == "nt":
                shell = shutil.which("pwsh") or shutil.which("powershell")
                process = subprocess.run(
                    [shell, "-NoProfile", "-NonInteractive", "-Command", f"{command}; exit $LASTEXITCODE"],
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
            else:
                process = subprocess.run(
                    ["/bin/sh", "-c", command],
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("usage:", process.stdout.casefold())
            self.assertFalse(config_dir.exists())


if __name__ == "__main__":
    unittest.main()
