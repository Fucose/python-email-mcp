import argparse
import contextlib
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from cli.main import build_parser, cmd_list, cmd_search, cmd_setup, cmd_view, main
from email_client.errors import DeliveryError
from email_client.models import Email


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


class DeliveryReportingTests(unittest.TestCase):
    def test_partial_delivery_exits_with_details_without_success_message(self):
        client = Mock()
        client.send_email.side_effect = DeliveryError(
            "partial",
            ["accepted@example.com"],
            {"rejected@example.com": {"code": 550, "message": "Refused"}},
            [],
            "Some recipients were refused",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = [
            "python-email-mcp", "send", "--to",
            "accepted@example.com,rejected@example.com",
            "--subject", "Test", "--body", "Body",
        ]
        with patch("cli.main.EmailClient", return_value=client), patch(
            "sys.argv", arguments
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 1)
        self.assertNotIn("发送成功", stdout.getvalue())
        self.assertIn("accepted@example.com", stderr.getvalue())
        self.assertIn("rejected@example.com", stderr.getvalue())
        self.assertIn('"code": 550', stderr.getvalue())
        client.disconnect.assert_called_once()


class DateDisplayTests(unittest.TestCase):
    def test_missing_dates_display_as_unknown_across_read_commands(self):
        message = Email("1", "Topic", "from@example.com", "to@example.com", datetime.min)
        client = Mock()
        client.get_recent_emails.return_value = [message]
        client.search_emails.return_value = [message]
        client.get_email.return_value = message
        args = argparse.Namespace(days=3, limit=20, subject="Topic", uid="1")
        for command in (cmd_list, cmd_search, cmd_view):
            with self.subTest(command=command.__name__):
                stdout = io.StringIO()
                with patch("cli.main.EmailClient", return_value=client), contextlib.redirect_stdout(stdout):
                    command(args)
                self.assertIn("日期不详", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
