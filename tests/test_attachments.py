import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

from email_client.imap_client import IMAPClient


class FakeIMAPConnection:
    def __init__(self, raw_message):
        self.raw_message = raw_message

    def uid(self, command, uid, query):
        return "OK", [(b"1 (RFC822 {123})", self.raw_message)]


class AttachmentTests(unittest.TestCase):
    def test_download_creates_folder_and_suffixes_duplicate_filename(self):
        message = EmailMessage()
        message["Subject"] = "attachments"
        message.set_content("body")
        message.add_attachment(b"new", maintype="application", subtype="octet-stream", filename="report.txt")

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "downloads"
            folder.mkdir()
            (folder / "report.txt").write_text("old", encoding="utf-8")
            client = IMAPClient("host", 993, "user", "secret")
            client.client = FakeIMAPConnection(message.as_bytes())
            files = client.download_attachments("1", folder)

            self.assertEqual(files, [folder / "report_1.txt"])
            self.assertEqual(files[0].read_bytes(), b"new")

    def test_attachment_filename_cannot_escape_destination(self):
        message = EmailMessage()
        message.set_content("body")
        message.add_attachment(b"safe", maintype="application", subtype="octet-stream", filename="../outside.txt")

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "downloads"
            client = IMAPClient("host", 993, "user", "secret")
            client.client = FakeIMAPConnection(message.as_bytes())
            files = client.download_attachments("1", folder)

            self.assertEqual(files, [folder / "outside.txt"])
            self.assertFalse((Path(temp_dir) / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
