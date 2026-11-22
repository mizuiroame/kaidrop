"""Downloading from a real FTP server on this computer (needs pyftpdlib; skipped without it)."""
import tempfile
import threading
import unittest
from pathlib import Path

from kaidrop.download import download, local_name, plan_download
from kaidrop.ftp import Choice, Connection, Status, connect

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    FTPServer = None


class LocalNameTest(unittest.TestCase):
    def test_names_windows_can_save(self):
        self.assertEqual(local_name("Why? Not.mp3"), "Why_ Not.mp3")
        self.assertEqual(local_name("a:b|c"), "a_b_c")
        self.assertEqual(local_name("trailing. "), "trailing")
        self.assertEqual(local_name("CON.txt"), "_CON.txt")
        self.assertEqual(local_name("Canción.flac"), "Canción.flac")  # Fine on Windows.


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.card = Path(self.tmp.name) / "card"
        self.here = Path(self.tmp.name) / "here"
        album = self.card / "Music" / "Album"
        album.mkdir(parents=True)
        self.here.mkdir()
        (album / "01 Song.flac").write_bytes(b"a" * 150_000)
        (album / "cover.jpg").write_bytes(b"jpg")
        (self.card / "Music" / "single.mp3").write_bytes(b"mp3")
        authorizer = DummyAuthorizer()
        authorizer.add_anonymous(str(self.card), perm="elradfmwMT")
        handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
        self.conn = Connection("127.0.0.1", self.server.address[1])

    def tearDown(self):
        self.server.close_all()
        self.tmp.cleanup()

    def plan(self, sources):
        ftp = connect(self.conn)
        try:
            return plan_download(ftp, sources, self.here)
        finally:
            ftp.quit()

    def run_download(self, plan, cancel=None, on_conflict=None):
        done = []
        counts = download(self.conn, plan, lambda *a: None, lambda i, item, st, msg: done.append((st, msg)),
                          cancel or threading.Event(), on_conflict)
        return counts, done

    def test_folder_and_file(self):
        plan = self.plan([("/Music/Album", True), ("/Music/single.mp3", False)])
        self.assertEqual(sorted(i.local.relative_to(self.here).as_posix() for i in plan.items),
                         ["Album/01 Song.flac", "Album/cover.jpg", "single.mp3"])
        self.assertEqual(plan.total_bytes, 150_006)
        counts, _ = self.run_download(plan)
        self.assertEqual(counts[Status.SENT], 3)
        self.assertEqual((self.here / "Album" / "01 Song.flac").read_bytes(), b"a" * 150_000)
        self.assertEqual(list(self.here.rglob("*.kaidrop-part")), [])

        counts, _ = self.run_download(plan)  # Again: the same sizes are skipped.
        self.assertEqual(counts[Status.SKIPPED], 3)

    def test_conflict_keep_both_and_cancel(self):
        plan = self.plan([("/Music/single.mp3", False)])
        (self.here / "single.mp3").write_bytes(b"other")
        asked = []

        def keep_both(item, here, server_time):
            asked.append((here.size, item.size))
            return Choice.KEEP_BOTH, False

        counts, done = self.run_download(plan, on_conflict=keep_both)
        self.assertEqual((counts[Status.COPY], asked), (1, [(5, 3)]))
        self.assertEqual((self.here / "single (2).mp3").read_bytes(), b"mp3")
        self.assertEqual((self.here / "single.mp3").read_bytes(), b"other")  # Left alone.

        cancel = threading.Event()
        cancel.set()
        counts, _ = self.run_download(self.plan([("/Music/Album", True)]), cancel)
        self.assertEqual(counts[Status.CANCELLED], 2)
        self.assertFalse((self.here / "Album" / "01 Song.flac").exists())


if __name__ == "__main__":
    unittest.main()
