import imaplib
import re
import socket
import threading
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from email_client.errors import AuthenticationError, InvalidArgumentError, NotFoundError, TransportError
from email_client.imap_client import IMAPClient


class RecordingConnection:
    def __init__(self):
        self.events = []
        self.state = "SELECTED"
        self.literal = None
        self.utf8_enabled = False
        self.fetch_response = ("OK", [])

    def starttls(self, ssl_context=None):
        self.events.append(("starttls", ssl_context))

    def login(self, user, password):
        self.events.append(("login", user, password))

    def select(self, mailbox, readonly=False):
        self.events.append(("select", mailbox, readonly))
        return "OK", [b"0"]

    def uid(self, command, *args):
        self.events.append(("uid", command, *args))
        if isinstance(self.fetch_response, Exception):
            raise self.fetch_response
        return self.fetch_response

    def logout(self):
        self.events.append(("logout",))
        self.state = "LOGOUT"

    def close(self):
        self.events.append(("close",))


class LiteralServer:
    """Small socket-pair server that records a real imaplib UID SEARCH command."""

    def __init__(self):
        self.client_socket, self.server_socket = socket.socketpair()
        self.command = None
        self.error = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            reader = self.server_socket.makefile("rb")
            self.server_socket.sendall(b"* OK test server ready\r\n")
            while True:
                line = reader.readline()
                if not line:
                    return
                tag = line.split(b" ", 1)[0]
                if b" CAPABILITY\r\n" in line:
                    self.server_socket.sendall(
                        b"* CAPABILITY IMAP4rev1 UTF8=ACCEPT\r\n"
                        + tag + b" OK capability completed\r\n"
                    )
                    continue

                match = re.search(rb" \{([0-9]+)\}\r\n$", line)
                if not match:
                    raise AssertionError(f"Expected a literal marker, got {line!r}")
                size = int(match.group(1))
                self.server_socket.sendall(b"+ send literal\r\n")
                literal = reader.read(size)
                ending = reader.read(2)
                self.command = (line, literal, ending)
                self.server_socket.sendall(
                    b"* SEARCH\r\n" + tag + b" OK search completed\r\n"
                )
                return
        except Exception as exc:  # captured so the test thread reports failures
            self.error = exc

    def close(self):
        self.client_socket.close()
        self.server_socket.close()
        self.thread.join(timeout=2)


class SocketIMAP4(imaplib.IMAP4):
    def __init__(self, sock):
        self._test_socket = sock
        super().__init__("socket-pair", 143)

    def open(self, host="", port=imaplib.IMAP4_PORT, timeout=None):
        self.sock = self._test_socket
        self.file = self.sock.makefile("rb")


class IMAPClientTests(unittest.TestCase):
    def test_ssl_connect_uses_verified_context_and_read_only_inbox(self):
        connection = RecordingConnection()
        context = object()
        client = IMAPClient("imap.example", 993, "user", "secret")

        with patch("email_client.imap_client.ssl.create_default_context", return_value=context), \
                patch("email_client.imap_client.imaplib.IMAP4_SSL", return_value=connection) as factory:
            self.assertTrue(client.connect())

        factory.assert_called_once_with("imap.example", 993, ssl_context=context)
        self.assertEqual(connection.events, [
            ("login", "user", "secret"),
            ("select", "INBOX", True),
        ])

    def test_plain_transport_starts_verified_tls_before_login(self):
        connection = RecordingConnection()
        context = object()
        client = IMAPClient("imap.example", 143, "user", "secret", ssl=False)

        with patch("email_client.imap_client.ssl.create_default_context", return_value=context), \
                patch("email_client.imap_client.imaplib.IMAP4", return_value=connection):
            client.connect()

        self.assertEqual(connection.events, [
            ("starttls", context),
            ("login", "user", "secret"),
            ("select", "INBOX", True),
        ])

    def test_starttls_failure_cleans_up_without_logging_in(self):
        connection = RecordingConnection()
        connection.starttls = Mock(side_effect=OSError("TLS failed"))
        client = IMAPClient("imap.example", 143, "user", "secret", ssl=False)

        with patch("email_client.imap_client.ssl.create_default_context", return_value=object()), \
                patch("email_client.imap_client.imaplib.IMAP4", return_value=connection):
            with self.assertRaises(TransportError):
                client.connect()

        self.assertEqual(connection.events, [("logout",)])
        self.assertIsNone(client.client)

    def test_authentication_failure_is_distinct_and_cleans_up(self):
        connection = RecordingConnection()
        connection.login = Mock(side_effect=imaplib.IMAP4.error("bad credentials"))
        client = IMAPClient("imap.example", 993, "user", "secret")

        with patch("email_client.imap_client.ssl.create_default_context", return_value=object()), \
                patch("email_client.imap_client.imaplib.IMAP4_SSL", return_value=connection):
            with self.assertRaises(AuthenticationError):
                client.connect()

        self.assertEqual(connection.events, [("logout",)])
        self.assertIsNone(client.client)

    def test_disconnect_logs_out_without_close_or_expunge(self):
        connection = RecordingConnection()
        client = IMAPClient("imap.example", 993, "user", "secret")
        client.client = connection

        client.disconnect()

        self.assertEqual(connection.events, [("logout",)])
        self.assertIsNone(client.client)

    def test_invalid_uids_are_rejected_before_connect_or_filesystem_changes(self):
        invalid_values = ("", "0", "1 2", "+1", "１", "4294967296", b"1\n")
        for uid in invalid_values:
            with self.subTest(uid=uid), TemporaryDirectory() as temp_dir:
                client = IMAPClient("imap.example", 993, "user", "secret")
                with patch.object(client, "connect") as connect:
                    with self.assertRaises(InvalidArgumentError):
                        client.get_email_content(uid)
                    folder = Path(temp_dir) / "attachments"
                    with self.assertRaises(InvalidArgumentError):
                        client.download_attachments(uid, folder)
                connect.assert_not_called()
                self.assertFalse(folder.exists())

    def test_batch_validates_every_uid_before_any_download(self):
        client = IMAPClient("imap.example", 993, "user", "secret")
        folder = Path("unused-attachments")

        with patch.object(client, "download_attachments") as download:
            with self.assertRaises(InvalidArgumentError):
                client.batch_download_attachments(["1", "bad"], folder)

        download.assert_not_called()

    def test_invalid_uid_from_search_is_a_transport_error_before_fetch(self):
        connection = RecordingConnection()
        connection.fetch_response = ("OK", [b"1 INVALID"])
        client = IMAPClient("imap.example", 993, "user", "secret")
        client.client = connection

        with self.assertRaises(TransportError):
            client.get_recent_emails()

        self.assertEqual(len(connection.events), 1)
        self.assertEqual(connection.events[0][1], "SEARCH")

    def test_uid_bounds_and_search_date_format(self):
        self.assertEqual(IMAPClient._validate_uid(b"4294967295"), "4294967295")
        self.assertEqual(IMAPClient._validate_uid("0007"), "7")
        self.assertEqual(IMAPClient._format_imap_date(date(2024, 3, 5)), "05-Mar-2024")
        with self.assertRaises(TransportError):
            IMAPClient._validate_uid(b"x", server_response=True)

    def test_search_rejects_line_breaks_and_nul_before_connect(self):
        client = IMAPClient("imap.example", 993, "user", "secret")
        for keyword in ("ok\r\nUID FETCH 1", "bad\x00text"):
            with self.subTest(keyword=keyword), patch.object(client, "connect") as connect:
                with self.assertRaises(InvalidArgumentError):
                    client.search_by_subject(keyword)
                connect.assert_not_called()

    def test_search_serializes_unicode_and_quotes_as_an_imap_literal(self):
        server = LiteralServer()
        imap_connection = SocketIMAP4(server.client_socket)
        imap_connection.state = "SELECTED"
        client = IMAPClient("unused", 143, "user", "secret", ssl=False)
        client.client = imap_connection
        keyword = 'café "quoted" \\ text) UID FETCH 99 BODY[]'

        try:
            self.assertEqual(client.search_by_subject(keyword), [])
            server.thread.join(timeout=2)
            self.assertIsNone(server.error)
            line, literal, ending = server.command
            self.assertRegex(
                line.decode("ascii"),
                r"^[A-Z0-9]+ UID SEARCH CHARSET UTF-8 SINCE [0-9]{2}-[A-Z][a-z]{2}-[0-9]{4} SUBJECT \{[0-9]+\}\r\n$",
            )
            self.assertNotIn(b"UID FETCH", line)
            self.assertEqual(literal, keyword.encode("utf-8"))
            self.assertEqual(ending, b"\r\n")
        finally:
            imap_connection.shutdown()
            server.close()

    def test_search_omits_charset_when_utf8_accept_is_enabled(self):
        server = LiteralServer()
        imap_connection = SocketIMAP4(server.client_socket)
        imap_connection.state = "SELECTED"
        imap_connection.utf8_enabled = True
        client = IMAPClient("unused", 143, "user", "secret", ssl=False)
        client.client = imap_connection

        try:
            self.assertEqual(client.search_by_subject("测试"), [])
            server.thread.join(timeout=2)
            self.assertIsNone(server.error)
            line, literal, _ = server.command
            self.assertIn(b" UID SEARCH SINCE ", line)
            self.assertNotIn(b"CHARSET", line)
            self.assertEqual(literal, "测试".encode("utf-8"))
        finally:
            imap_connection.shutdown()
            server.close()

    def test_fetch_uses_peek_and_populates_reply_headers(self):
        raw_message = (
            b"Subject: hello\r\nFrom: sender@example.com\r\nTo: user@example.com\r\n"
            b"Date: Tue, 03 Jan 2023 10:00:00 +0000\r\n"
            b"Reply-To: replies@example.com\r\nMessage-ID: <m1@example.com>\r\n"
            b"References: <m0@example.com>\r\n\t<m-minus-one@example.com>\r\n\r\nbody"
        )
        connection = RecordingConnection()
        connection.fetch_response = ("OK", [(b"7 (BODY[HEADER])", raw_message)])
        client = IMAPClient("imap.example", 993, "user", "secret")
        client.client = connection

        result = client._fetch_email_by_uid(b"7")

        self.assertEqual(connection.events, [("uid", "FETCH", "7", "(BODY.PEEK[HEADER])")])
        self.assertEqual(result.reply_to, "replies@example.com")
        self.assertEqual(result.message_id, "<m1@example.com>")
        self.assertEqual(
            result.references,
            "<m0@example.com> <m-minus-one@example.com>",
        )

    def test_parse_unfolds_subject_and_recipient_header_continuations(self):
        raw_message = (
            b"Subject: Budget forecast\r\n\tfor Q4\r\n"
            b"From: sender@example.com\r\n"
            b"To: First <first@example.com>,\r\n\tSecond <second@example.com>\r\n"
            b"Cc: Finance <finance@example.com>,\r\n\tLegal <legal@example.com>\r\n"
            b"Date: Mon, 02 Nov 2026 10:00:00 +0000\r\n\r\nbody"
        )
        connection = RecordingConnection()
        connection.fetch_response = ("OK", [(b"8 (BODY[HEADER])", raw_message)])
        client = IMAPClient("imap.example", 993, "user", "secret")
        client.client = connection

        result = client._fetch_email_by_uid("8")

        self.assertEqual(result.subject, "Budget forecast for Q4")
        self.assertEqual(
            result.to,
            "First <first@example.com>, Second <second@example.com>",
        )
        self.assertEqual(
            result.cc,
            "Finance <finance@example.com>, Legal <legal@example.com>",
        )
        malformed_line_break = "subject\r\nInjected: value"
        self.assertEqual(IMAPClient._decode_str(malformed_line_break), malformed_line_break)

    def test_missing_or_invalid_date_uses_deterministic_sentinel(self):
        for date_header in (b"", b"Date: not a valid date\r\n"):
            with self.subTest(date_header=date_header):
                raw_message = (
                    b"Subject: no usable date\r\nFrom: sender@example.com\r\n"
                    b"To: user@example.com\r\n" + date_header + b"\r\nbody"
                )
                connection = RecordingConnection()
                connection.fetch_response = ("OK", [(b"9 (BODY[HEADER])", raw_message)])
                client = IMAPClient("imap.example", 993, "user", "secret")
                client.client = connection

                result = client._fetch_email_by_uid("9")

                self.assertEqual(result.date, datetime.min)

    def test_fetch_transport_failures_are_not_reported_as_not_found(self):
        connection = RecordingConnection()
        connection.fetch_response = OSError("socket closed")
        client = IMAPClient("imap.example", 993, "user", "secret")
        client.client = connection

        with self.assertRaises(TransportError):
            client.get_email_content("1")

        self.assertEqual(
            connection.events,
            [("uid", "FETCH", "1", "(BODY.PEEK[])")],
        )

    def test_missing_fetch_payload_remains_not_found_for_attachment_download(self):
        connection = RecordingConnection()
        connection.fetch_response = ("OK", [])
        client = IMAPClient("imap.example", 993, "user", "secret")
        client.client = connection

        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(NotFoundError):
                client.download_attachments("1", Path(temp_dir) / "attachments")

        self.assertEqual(connection.events, [
            ("uid", "FETCH", "1", "(BODY.PEEK[])")
        ])


if __name__ == "__main__":
    unittest.main()
