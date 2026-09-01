import unittest
from datetime import datetime
from unittest.mock import Mock

from email_client.models import Email
from email_client.smtp_client import SMTPClient


class ReplyRecipientTests(unittest.TestCase):
    def test_reply_all_includes_sender_and_excludes_own_address(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.send_email = Mock(return_value=True)
        original = Email(
            uid="1",
            subject="Topic",
            from_="Sender <sender@example.com>",
            to="Me <me@example.com>, Other <other@example.com>",
            cc="Copy <copy@example.com>, sender@example.com",
            date=datetime(2026, 1, 1),
            body="Original",
        )

        client.reply_email(original, "Reply", reply_all=True)

        kwargs = client.send_email.call_args.kwargs
        self.assertEqual(kwargs["to"], ["sender@example.com", "other@example.com"])
        self.assertEqual(kwargs["cc"], ["copy@example.com"])
        self.assertNotIn("me@example.com", kwargs["to"] + kwargs["cc"])


if __name__ == "__main__":
    unittest.main()
