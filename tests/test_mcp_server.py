import contextlib
import io
import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

try:
    from mcp_server.server import execute_tool
except ModuleNotFoundError as exc:
    if exc.name == "mcp":
        execute_tool = None
    else:
        raise

from email_client.errors import AuthenticationError, ConfigurationError, DeliveryError
from email_client.models import Email
from email_client.smtp_client import SMTPClient


@unittest.skipIf(execute_tool is None, "mcp dependency is not installed in this interpreter")
class MCPToolTests(unittest.TestCase):
    def test_query_returns_envelope_and_closes_fresh_client(self):
        class FakeClient:
            def __init__(self):
                self.disconnected = False

            def get_recent_emails(self, days, limit):
                return [Email("42", "Subject", "from@example.com", "to@example.com", datetime(2026, 1, 2, 3, 4, 5))]

            def disconnect(self):
                self.disconnected = True

        created = []

        def factory():
            client = FakeClient()
            created.append(client)
            return client

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = execute_tool("get_recent_emails", {"days": 3, "limit": 10}, client_factory=factory)

        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["emails"][0]["uid"], "42")
        self.assertTrue(created[0].disconnected)

    def test_invalid_argument_has_stable_code_and_closes_client(self):
        client = Mock()
        result = execute_tool("get_recent_emails", {"days": 0}, client_factory=lambda: client)
        self.assertEqual(result["error"]["code"], "invalid_argument")
        client.disconnect.assert_called_once()

    def test_authentication_failure_has_stable_code(self):
        class FakeClient:
            def get_recent_emails(self, days, limit):
                raise AuthenticationError("IMAP authentication failed")

            def disconnect(self):
                pass

        result = execute_tool("get_recent_emails", {}, client_factory=FakeClient)
        self.assertEqual(result["error"]["code"], "authentication_failed")

    def test_not_configured_includes_setup_guidance_without_secret(self):
        class FakeClient:
            def get_recent_emails(self, days, limit):
                raise ConfigurationError(["EMAIL_PASSWORD"])

            def disconnect(self):
                pass

        result = execute_tool("get_recent_emails", {}, client_factory=FakeClient)
        self.assertEqual(result["error"]["code"], "not_configured")
        serialized = repr(result)
        self.assertIn("setup_command", serialized)
        self.assertNotIn("authorization", serialized.lower())

    def test_missing_email_is_not_found(self):
        client = Mock()
        client.get_email.return_value = None
        result = execute_tool("get_email_content", {"uid": "404"}, client_factory=lambda: client)
        self.assertEqual(result["error"]["code"], "not_found")
        client.disconnect.assert_called_once()

    def test_unknown_dates_serialize_as_null_across_read_tools(self):
        message = Email("1", "Topic", "from@example.com", "to@example.com", datetime.min)
        client = Mock()
        client.get_recent_emails.return_value = [message]
        client.search_emails.return_value = [message]
        client.get_email.return_value = message
        for name, arguments in (
            ("get_recent_emails", {}),
            ("search_emails", {"subject": "Topic"}),
            ("get_email_content", {"uid": "1"}),
        ):
            with self.subTest(tool=name):
                result = execute_tool(name, arguments, client_factory=lambda: client)
                data = result["data"]
                summary = data if name == "get_email_content" else data["emails"][0]
                self.assertIsNone(summary["date"])

    def test_search_and_download_tools_return_structured_data(self):
        client = Mock()
        message = Email("7", "Budget", "a@example.com", "b@example.com", datetime(2026, 2, 3))
        client.search_emails.return_value = [message]
        client.download_attachments.return_value = [Path("downloaded.txt")]
        client.batch_download_attachments.return_value = [Path("batch.txt")]

        search = execute_tool(
            "search_emails", {"subject": "Budget", "days": 10}, client_factory=lambda: client
        )
        download = execute_tool(
            "download_attachments", {"uid": "7", "folder": "."}, client_factory=lambda: client
        )
        batch = execute_tool(
            "batch_download_attachments",
            {"subject": "Budget", "days": 10, "folder": "."},
            client_factory=lambda: client,
        )

        self.assertEqual(search["data"]["count"], 1)
        self.assertEqual(download["data"]["count"], 1)
        self.assertEqual(batch["data"]["count"], 1)
        self.assertEqual(client.disconnect.call_count, 3)

    def test_send_and_reply_validate_then_call_client(self):
        client = Mock()
        smtp = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        smtp.set_signature("My signature")
        client.prepare_email.side_effect = smtp.prepare_email
        original = Email(
            "9", "Topic", "a@example.com", "me@example.com", datetime(2026, 1, 1),
            reply_to="reply@example.com", message_id="<original@example.com>",
            body="Original",
        )

        def prepare_reply(uid, body, attachments, reply_all):
            return smtp.prepare_reply(original, body, attachments, reply_all)

        client.prepare_reply.side_effect = prepare_reply
        send_args = {"to": ["to@example.com"], "subject": "Hello", "text": "Body"}
        reply_args = {"uid": "9", "text": "Reply", "reply_all": True}
        send_preview = execute_tool("preview_email", send_args, client_factory=lambda: client)
        reply_preview = execute_tool("preview_reply", reply_args, client_factory=lambda: client)
        self.assertEqual(client.send_prepared_email.call_count, 0)
        self.assertIn("My signature", send_preview["data"]["email"]["text"])
        self.assertIn("Original", reply_preview["data"]["email"]["text"])
        self.assertEqual(reply_preview["data"]["email"]["to"], ["reply@example.com"])
        send = execute_tool(
            "send_email",
            {**send_args, "preview_id": send_preview["data"]["preview_id"]},
            client_factory=lambda: client,
        )
        reply = execute_tool(
            "reply_email",
            {**reply_args, "preview_id": reply_preview["data"]["preview_id"]},
            client_factory=lambda: client,
        )

        self.assertTrue(send["ok"])
        self.assertTrue(reply["ok"])
        self.assertEqual(send["data"]["accepted"], ["to@example.com"])
        self.assertEqual(reply["data"]["accepted"], ["reply@example.com"])
        self.assertEqual(client.send_prepared_email.call_count, 2)
        self.assertEqual(client.disconnect.call_count, 4)

    def test_sending_requires_matching_preview_before_execution(self):
        client = Mock()
        smtp = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.prepare_email.side_effect = smtp.prepare_email
        arguments = {"to": ["to@example.com"], "subject": "Hello", "text": "Body"}
        missing = execute_tool("send_email", arguments, client_factory=lambda: client)
        self.assertEqual(missing["error"]["code"], "invalid_argument")
        client.prepare_email.assert_not_called()
        preview = execute_tool("preview_email", arguments, client_factory=lambda: client)
        preview_id = preview["data"]["preview_id"]
        for change in ({"text": "Changed"}, {"bcc": ["hidden@example.com"]}):
            with self.subTest(change=change):
                result = execute_tool("send_email", {**arguments, **change, "preview_id": preview_id}, client_factory=lambda: client)
                self.assertEqual(result["error"]["code"], "invalid_argument")
        smtp.set_signature("New signature")
        changed_signature = execute_tool(
            "send_email", {**arguments, "preview_id": preview_id},
            client_factory=lambda: client,
        )
        self.assertEqual(changed_signature["error"]["code"], "invalid_argument")
        client.send_prepared_email.assert_not_called()

    def test_changed_attachment_content_invalidates_preview(self):
        client = Mock()
        smtp = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.prepare_email.side_effect = smtp.prepare_email
        with tempfile.TemporaryDirectory() as temporary:
            attachment = Path(temporary) / "report.txt"
            attachment.write_bytes(b"first")
            arguments = {
                "to": ["to@example.com"], "subject": "Report", "text": "Body",
                "attachments": [str(attachment)],
            }
            preview = execute_tool("preview_email", arguments, client_factory=lambda: client)
            attachment.write_bytes(b"other")
            result = execute_tool(
                "send_email", {**arguments, "preview_id": preview["data"]["preview_id"]},
                client_factory=lambda: client,
            )
        self.assertEqual(result["error"]["code"], "invalid_argument")
        client.send_prepared_email.assert_not_called()

    def test_delivery_failure_preserves_per_recipient_details(self):
        client = Mock()
        smtp = SMTPClient("smtp.example.com", 465, "me@example.com", "secret")
        client.prepare_email.side_effect = smtp.prepare_email
        error = DeliveryError(
            "partial", ["accepted@example.com"],
            {"rejected@example.com": {"code": 550, "message": "Refused"}},
            [], "Some recipients were refused",
        )
        client.send_prepared_email.side_effect = error
        arguments = {
            "to": ["accepted@example.com", "rejected@example.com"],
            "subject": "Hello", "text": "Body",
        }
        preview = execute_tool("preview_email", arguments, client_factory=lambda: client)
        result = execute_tool(
            "send_email", {**arguments, "preview_id": preview["data"]["preview_id"]},
            client_factory=lambda: client,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "delivery_failed")
        self.assertEqual(result["error"]["details"], error.details)
        self.assertIsNone(result["data"])

    def test_tool_annotations_and_required_preview_fields(self):
        from mcp_server.server import list_tools

        tools = {tool.name: tool for tool in asyncio.run(list_tools())}
        for name in ("preview_email", "preview_reply", "get_email_content"):
            self.assertTrue(tools[name].annotations.readOnlyHint)
        for name in ("send_email", "reply_email"):
            self.assertFalse(tools[name].annotations.readOnlyHint)
            self.assertFalse(tools[name].annotations.idempotentHint)
            self.assertIn("preview_id", tools[name].inputSchema["required"])

    def test_test_connection_surfaces_authentication_failure(self):
        client = Mock()
        client.test_connection.return_value = {
            "imap": {"ok": False, "code": "authentication_failed", "message": "failed"}
        }
        result = execute_tool(
            "test_connection", {"test_type": "imap"}, client_factory=lambda: client
        )
        self.assertEqual(result["error"]["code"], "authentication_failed")
        client.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
