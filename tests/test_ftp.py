"""Uploads to a real FTP server on this computer (needs pyftpdlib; skipped
without it)."""
import tempfile
import threading
import unittest
from pathlib import Path

from kaidrop.ftp import Connection, Status, test_connection, upload
from kaidrop.plan import build_plan

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    FTPServer = None


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class FtpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local = Path(self.tmp.name) / "local"
        self.card = Path(self.tmp.name) / "card"
        (self.local / "Disco Ñ").mkdir(parents=True)
        self.card.mkdir()
        (self.local / "Disco Ñ" / "01 Canción.flac").write_bytes(b"a" * 200_000)
        (self.local / "Disco Ñ" / "cover.jpg").write_bytes(b"jpg")
        authorizer = DummyAuthorizer()
        authorizer.add_anonymous(str(self.card), perm="elradfmwMT")
        handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
        self.conn = Connection("127.0.0.1", self.server.address[1])

    def tearDown(self):
        self.server.close_all()
        self.tmp.cleanup()

    def run_upload(self, cancel=None):
        plan = build_plan([self.local / "Disco Ñ"], "/Music")
        done = []
        counts = upload(self.conn, plan, lambda *a: None, lambda i, item, status, msg: done.append(status),
                        cancel or threading.Event())
        return counts, done

    def test_connect(self):
        self.assertTrue(test_connection(self.conn).startswith("220"))

    def test_upload_then_skip(self):
        counts, _ = self.run_upload()
        self.assertEqual(counts[Status.SENT], 2)
        sent = self.card / "Music" / "Disco N" / "01 Cancion.flac"
        self.assertEqual(sent.read_bytes(), b"a" * 200_000)
        self.assertTrue((self.local / "Disco Ñ" / "01 Canción.flac").exists())  # Local names untouched.
        counts, _ = self.run_upload()
        self.assertEqual(counts[Status.SKIPPED], 2)

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        counts, done = self.run_upload(cancel)
        self.assertEqual(counts[Status.CANCELLED], 2)
        self.assertFalse((self.card / "Music" / "Disco N" / "01 Cancion.flac").exists())


if __name__ == "__main__":
    unittest.main()
