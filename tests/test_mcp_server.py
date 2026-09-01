import contextlib
import io
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

from email_client.errors import AuthenticationError, ConfigurationError
from email_client.models import Email


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
        send = execute_tool(
            "send_email",
            {"to": ["to@example.com"], "subject": "Hello", "text": "Body"},
            client_factory=lambda: client,
        )
        reply = execute_tool(
            "reply_email",
            {"uid": "9", "text": "Reply", "reply_all": True},
            client_factory=lambda: client,
        )

        self.assertTrue(send["ok"])
        self.assertTrue(reply["ok"])
        client.send_email.assert_called_once()
        client.reply.assert_called_once_with("9", "Reply", None, True)
        self.assertEqual(client.disconnect.call_count, 2)

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
