import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from email_client.client import EmailClient
from email_client.errors import InvalidArgumentError


class ClientEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.config = Mock()
        self.config.get_imap_config.return_value = (
            "imap.example.com", 993, "me@example.com", "secret", True
        )
        self.config.get_smtp_config.return_value = (
            "smtp.example.com", 465, "me@example.com", "secret", True
        )
        self.config.load_signature.return_value = "My signature"
        self.client = EmailClient(self.config)
        self.addCleanup(self.client.disconnect)

    def test_preparation_does_not_connect_smtp(self):
        with patch("email_client.smtp_client.smtplib.SMTP_SSL") as connection:
            plan = self.client.prepare_email(["to@example.com"], "Subject", "Body")
        connection.assert_not_called()
        self.assertEqual(plan.preview()["text"], "Body\n\nMy signature")

    def test_invalid_uid_does_not_connect_imap(self):
        with patch("email_client.imap_client.imaplib.IMAP4_SSL") as connection:
            with self.assertRaises(InvalidArgumentError):
                self.client.get_email("1\r\nA LOGOUT")
        connection.assert_not_called()

    def test_test_connection_explicitly_connects_each_lazy_client(self):
        with patch("email_client.imap_client.imaplib.IMAP4_SSL") as imap, patch(
            "email_client.smtp_client.smtplib.SMTP_SSL"
        ) as smtp:
            imap.return_value.select.return_value = ("OK", [b"0"])
            result = self.client.test_connection()
        self.assertTrue(result["imap"]["ok"])
        self.assertTrue(result["smtp"]["ok"])
        imap.return_value.login.assert_called_once()
        smtp.return_value.login.assert_called_once()
        imap.return_value.logout.assert_called_once()
        smtp.return_value.quit.assert_called_once()

    def test_send_reports_partial_refusal_through_high_level_client(self):
        from email_client.errors import DeliveryError

        with patch("email_client.smtp_client.smtplib.SMTP_SSL") as connection:
            connection.return_value.send_message.return_value = {
                "rejected@example.com": (550, b"Refused")
            }
            with self.assertRaises(DeliveryError) as raised:
                self.client.send_email(
                    ["accepted@example.com", "rejected@example.com"], "Subject", "Body"
                )
        self.assertEqual(raised.exception.details["accepted"], ["accepted@example.com"])
        self.assertEqual(raised.exception.details["rejected"]["rejected@example.com"]["code"], 550)

    def test_reply_preview_is_stable_when_original_date_is_missing_or_invalid(self):
        connection = Mock()
        self.client._imap().client = connection
        for date_header in (b"", b"Date: invalid\r\n"):
            with self.subTest(date_header=date_header):
                raw_message = (
                    b"From: sender@example.com\r\n"
                    b"To: me@example.com\r\n"
                    b"Subject: Topic\r\n"
                    b"Message-ID: <original@example.com>\r\n"
                    + date_header + b"\r\nOriginal body"
                )
                connection.uid.return_value = ("OK", [(b"1", raw_message)])
                with patch("email_client.imap_client.datetime") as parsed_datetime:
                    parsed_datetime.min = datetime.min
                    parsed_datetime.now.side_effect = [
                        datetime(2026, 1, 1, 10, 59),
                        datetime(2026, 1, 1, 11, 0),
                    ]
                    preview = self.client.prepare_reply("1", "Reply")
                    execution = self.client.prepare_reply("1", "Reply")
                self.assertEqual(preview.preview_id, execution.preview_id)
                self.assertIn("日期不详", preview.text)


if __name__ == "__main__":
    unittest.main()
