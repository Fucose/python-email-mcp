import json
import smtplib
import tempfile
import unittest
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from unittest.mock import Mock, patch

from email_client.errors import DeliveryError, InvalidArgumentError, TransportError
from email_client.models import Email
from email_client.smtp_client import SMTPClient


def original_email(**changes):
    values = {
        "uid": "1",
        "subject": "Topic",
        "from_": "Sender <sender@example.com>",
        "to": "Me <me@example.com>, Other <other@example.com>",
        "cc": "Copy <copy@example.com>, sender@example.com",
        "date": datetime(2026, 1, 1),
        "body": "Original",
    }
    values.update(changes)
    return Email(**values)


class SMTPConnectionTests(unittest.TestCase):
    @patch("email_client.smtp_client.ssl_module.create_default_context")
    @patch("email_client.smtp_client.smtplib.SMTP_SSL")
    def test_smtp_ssl_uses_default_verifying_context(self, smtp_ssl, create_context):
        context = Mock()
        create_context.return_value = context
        smtp = Mock()
        smtp_ssl.return_value = smtp
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")

        self.assertTrue(client.connect())

        smtp_ssl.assert_called_once_with("smtp.example.com", 465, context=context)
        smtp.login.assert_called_once_with("me@example.com", "secret")

    @patch("email_client.smtp_client.ssl_module.create_default_context")
    @patch("email_client.smtp_client.smtplib.SMTP")
    def test_starttls_uses_context_before_authentication(self, smtp_factory, create_context):
        context = Mock()
        create_context.return_value = context
        events = []
        smtp = Mock()
        smtp.starttls.side_effect = lambda **kwargs: events.append(("starttls", kwargs))
        smtp.login.side_effect = lambda *args: events.append(("login", args))
        smtp_factory.return_value = smtp
        client = SMTPClient("smtp.example.com", 587, "me@example.com", "secret", ssl=False)

        self.assertTrue(client.connect())

        smtp_factory.assert_called_once_with("smtp.example.com", 587)
        self.assertEqual(events[0], ("starttls", {"context": context}))
        self.assertEqual(events[1], ("login", ("me@example.com", "secret")))

    @patch("email_client.smtp_client.smtplib.SMTP")
    def test_starttls_failure_cleans_up_without_authenticating(self, smtp_factory):
        smtp = Mock()
        smtp.starttls.side_effect = RuntimeError("TLS negotiation failed")
        smtp_factory.return_value = smtp
        client = SMTPClient("smtp.example.com", 587, "me@example.com", "secret", ssl=False)

        with self.assertRaises(TransportError):
            client.connect()

        smtp.login.assert_not_called()
        smtp.quit.assert_called_once_with()
        self.assertIsNone(client.client)


class ReplyPreparationTests(unittest.TestCase):
    def test_reply_to_preferred_with_multiple_addresses_and_thread_headers(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        original = original_email(
            reply_to="First <reply1@example.com>,\r\n\treply2@example.com",
            to="Me <me@example.com>,\r\n Other <other@example.com>, reply1@example.com",
            cc="Copy <copy@example.com>, other@example.com, Me <me@example.com>",
            message_id="<current@example.com>",
            references="<root@example.com>\r\n\t<older@example.com>",
        )

        plan = client.prepare_reply(original, "Reply", reply_all=True)

        self.assertEqual(
            plan.to,
            ("reply1@example.com", "reply2@example.com", "other@example.com"),
        )
        self.assertEqual(plan.cc, ("copy@example.com",))
        self.assertEqual(plan.in_reply_to, "<current@example.com>")
        self.assertEqual(
            plan.references,
            "<root@example.com> <older@example.com> <current@example.com>",
        )
        self.assertNotIn("me@example.com", plan.to + plan.cc)
        self.assertNotIn("sender@example.com", plan.to + plan.cc)
        self.assertEqual(plan.subject, "Re: Topic")
        self.assertEqual(plan.preview()["to"], list(plan.to))

        message = client._build_message(plan)
        self.assertEqual(message["In-Reply-To"], "<current@example.com>")
        self.assertEqual(
            message["References"],
            "<root@example.com> <older@example.com> <current@example.com>",
        )

    def test_single_reply_uses_reply_to_and_signature_once(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.set_signature("Regards")
        original = original_email(reply_to="reply@example.com")

        plan = client.prepare_reply(original, "Reply")

        self.assertEqual(plan.to, ("reply@example.com",))
        self.assertEqual(plan.cc, ())
        self.assertEqual(plan.text.count("Regards"), 1)
        self.assertIn("-----原始邮件-----", plan.text)

    def test_unknown_original_date_has_stable_reply_preview(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        original = original_email(date=datetime.min)

        first_plan = client.prepare_reply(original, "Reply")
        second_plan = client.prepare_reply(original, "Reply")

        self.assertIn("日期: 日期不详", first_plan.text)
        self.assertEqual(first_plan.text, second_plan.text)
        self.assertEqual(first_plan.preview_id, second_plan.preview_id)

    def test_reply_all_deduplicates_to_and_cc_and_excludes_own_address(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        original = original_email()

        plan = client.prepare_reply(original, "Reply", reply_all=True)

        self.assertEqual(plan.to, ("sender@example.com", "other@example.com"))
        self.assertEqual(plan.cc, ("copy@example.com",))


class PreparedEmailTests(unittest.TestCase):
    def test_attachment_snapshot_and_preview_id_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            attachment_path = Path(directory) / "report.txt"
            attachment_path.write_bytes(b"first version")
            client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
            client.set_signature("Regards")
            plan = client.prepare_email(
                ["To <TO@example.com>"],
                "Subject",
                "Body",
                [attachment_path],
                cc=["cc@example.com"],
                bcc=["bcc@example.com"],
            )
            preview = plan.preview()
            preview_id = plan.preview_id
            self.assertEqual(preview["preview_id"], preview_id)
            self.assertEqual(preview["to"], ["TO@example.com"])
            self.assertEqual(preview["attachments"], [str(attachment_path.resolve())])
            self.assertEqual(preview["attachment_details"][0]["size"], 13)
            self.assertEqual(json.loads(json.dumps(preview)), preview)
            self.assertEqual(plan.text, "Body\n\nRegards")

            attachment_path.write_bytes(b"second version")
            self.assertEqual(plan.preview_id, preview_id)
            self.assertEqual(plan.attachments[0].content, b"first version")

            smtp = Mock()
            smtp.send_message.return_value = {}
            client.client = smtp
            self.assertTrue(client.send_prepared_email(plan))
            args, kwargs = smtp.send_message.call_args
            message = args[0]
            self.assertEqual(
                kwargs["to_addrs"],
                ["TO@example.com", "cc@example.com", "bcc@example.com"],
            )
            parsed = BytesParser(policy=default).parsebytes(message.as_bytes())
            self.assertIsNone(parsed.get("Bcc"))
            self.assertEqual(parsed.get_payload()[1].get_payload(decode=True), b"first version")

            changed_plan = client.prepare_email(
                ["TO@example.com"], "Subject", "Body", [attachment_path],
                cc=["cc@example.com"], bcc=["bcc@example.com"],
            )
            self.assertNotEqual(changed_plan.preview_id, preview_id)

    def test_invalid_headers_and_recipients_fail_before_connecting(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.connect = Mock()

        with self.assertRaises(InvalidArgumentError):
            client.send_email(["to@example.com"], "Subject\r\nBcc: bad@example.com", "Body")
        with self.assertRaises(InvalidArgumentError):
            client.send_email(["not-an-address"], "Subject", "Body")
        with self.assertRaises(InvalidArgumentError):
            client.send_email([], "Subject", "Body")

        client.connect.assert_not_called()

    def test_send_email_and_reply_email_keep_true_on_acceptance(self):
        client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.client = Mock()
        client.client.send_message.return_value = {}

        self.assertIs(client.send_email(["to@example.com"], "Subject", "Body"), True)
        self.assertIs(client.reply_email(original_email(), "Reply"), True)


class DeliveryOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.client = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        self.plan = self.client.prepare_email(
            ["good@example.com", "bad@example.com"],
            "Subject",
            "Body",
        )
        self.client.client = Mock()

    def test_partial_recipient_refusal_reports_accepted_and_rejected(self):
        self.client.client.send_message.return_value = {
            "bad@example.com": (550, b"Mailbox unavailable"),
        }

        with self.assertRaises(DeliveryError) as caught:
            self.client.send_prepared_email(self.plan)

        self.assertEqual(
            caught.exception.details,
            {
                "status": "partial",
                "accepted": ["good@example.com"],
                "rejected": {
                    "bad@example.com": {
                        "code": 550,
                        "message": "Mailbox unavailable",
                    },
                },
                "unknown": [],
            },
        )

    def test_delivery_results_preserve_recipient_spelling(self):
        plan = self.client.prepare_email(
            ["Good@Example.com", "Bad@Example.com"],
            "Subject",
            "Body",
        )
        self.client.client.send_message.return_value = {
            "bad@example.com": (550, b"Mailbox unavailable"),
        }

        with self.assertRaises(DeliveryError) as caught:
            self.client.send_prepared_email(plan)

        self.assertEqual(caught.exception.details["accepted"], ["Good@Example.com"])
        self.assertEqual(
            caught.exception.details["rejected"],
            {
                "Bad@Example.com": {
                    "code": 550,
                    "message": "Mailbox unavailable",
                },
            },
        )

    def test_all_refused_exception_reports_every_rejection(self):
        plan = self.client.prepare_email(["bad@example.com"], "Subject", "Body")
        self.client.client.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"bad@example.com": (550, b"Mailbox unavailable")}
        )

        with self.assertRaises(DeliveryError) as caught:
            self.client.send_prepared_email(plan)

        self.assertEqual(caught.exception.details["status"], "rejected")
        self.assertEqual(caught.exception.details["accepted"], [])
        self.assertEqual(
            caught.exception.details["rejected"]["bad@example.com"]["code"],
            550,
        )
        self.assertEqual(caught.exception.details["unknown"], [])

    def test_data_rejection_marks_all_recipients_rejected(self):
        self.client.client.send_message.side_effect = smtplib.SMTPDataError(
            554,
            b"Message rejected",
        )

        with self.assertRaises(DeliveryError) as caught:
            self.client.send_prepared_email(self.plan)

        self.assertEqual(caught.exception.details["status"], "rejected")
        self.assertEqual(caught.exception.details["accepted"], [])
        self.assertEqual(
            set(caught.exception.details["rejected"]),
            {"good@example.com", "bad@example.com"},
        )
        self.assertTrue(
            all(item["code"] == 554 for item in caught.exception.details["rejected"].values())
        )

    def test_sender_rejection_marks_all_recipients_rejected(self):
        self.client.client.send_message.side_effect = smtplib.SMTPSenderRefused(
            550,
            b"Sender rejected",
            "me@example.com",
        )

        with self.assertRaises(DeliveryError) as caught:
            self.client.send_prepared_email(self.plan)

        self.assertEqual(caught.exception.details["status"], "rejected")
        self.assertEqual(caught.exception.details["accepted"], [])
        self.assertEqual(
            set(caught.exception.details["rejected"]),
            {"good@example.com", "bad@example.com"},
        )

    def test_transport_error_during_send_marks_all_outcomes_unknown(self):
        self.client.client.send_message.side_effect = OSError("connection lost")

        with self.assertRaises(DeliveryError) as caught:
            self.client.send_prepared_email(self.plan)

        self.assertEqual(caught.exception.details["status"], "unknown")
        self.assertEqual(caught.exception.details["accepted"], [])
        self.assertEqual(caught.exception.details["rejected"], {})
        self.assertEqual(
            caught.exception.details["unknown"],
            ["good@example.com", "bad@example.com"],
        )


if __name__ == "__main__":
    unittest.main()
