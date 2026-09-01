import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cli.main import build_parser, cmd_setup


class SetupTests(unittest.TestCase):
    def test_setup_uses_getpass_and_never_prints_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Mock()
            config.env_file = Path(temp_dir) / "config.env"
            config.save_config.return_value = True
            args = argparse.Namespace(
                email="user@example.com",
                imap_host="imap.example.com",
                imap_port=993,
                imap_ssl=True,
                smtp_host="smtp.example.com",
                smtp_port=465,
                smtp_ssl=True,
                force=False,
            )
            stdout = io.StringIO()
            with patch("cli.main.Config", return_value=config), patch(
                "cli.main.getpass.getpass", return_value="top-secret"
            ) as getpass_mock, contextlib.redirect_stdout(stdout):
                cmd_setup(args)

            getpass_mock.assert_called_once()
            self.assertNotIn("top-secret", stdout.getvalue())
            self.assertEqual(config.save_config.call_args.kwargs["password"], "top-secret")

    def test_existing_config_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "config.env"
            existing.touch()
            config = Mock(env_file=existing)
            args = argparse.Namespace(force=False)
            with patch("cli.main.Config", return_value=config), patch(
                "builtins.input", return_value="n"
            ), contextlib.redirect_stdout(io.StringIO()):
                cmd_setup(args)
            config.save_config.assert_not_called()

    def test_password_cannot_be_supplied_as_command_line_argument(self):
        parser = build_parser()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["setup", "--password", "secret"])


if __name__ == "__main__":
    unittest.main()
