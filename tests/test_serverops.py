"""Moving and copying on a real FTP server on this computer (needs
pyftpdlib; skipped without it)."""
import ftplib
import tempfile
import threading
import unittest
from pathlib import Path

from kaidrop.serverops import copy_items, inside, move_items

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    FTPServer = None


class InsideTest(unittest.TestCase):
    def test_inside(self):
        self.assertTrue(inside("/Videos/Series", "/Videos"))
        self.assertTrue(inside("/Videos", "/Videos/"))
        self.assertFalse(inside("/Videos2", "/Videos"))
        self.assertTrue(inside("/anything", "/"))


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class ServerOpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.card = Path(self.tmp.name)
        (self.card / "Videos" / "Show").mkdir(parents=True)
        (self.card / "Videos" / "Show" / "e1.mkv").write_bytes(b"a" * 100_000)
        (self.card / "Videos" / "Show" / "e2.mkv").write_bytes(b"b" * 10)
        (self.card / "Videos" / "film.mp4").write_bytes(b"f" * 5000)
        (self.card / "Inbox").mkdir()
        (self.card / "Inbox" / "film.mp4").write_bytes(b"other")
        authorizer = DummyAuthorizer()
        authorizer.add_anonymous(str(self.card), perm="elradfmwMT")
        handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
        self.ftp = ftplib.FTP()
        self.ftp.connect("127.0.0.1", self.server.address[1])
        self.ftp.login()

    def tearDown(self):
        self.ftp.close()
        self.server.close_all()
        self.tmp.cleanup()

    def test_move_files_and_folders(self):
        notes = move_items(self.ftp, [("/Videos/Show", True), ("/Videos/film.mp4", False)], "/Inbox")
        self.assertTrue((self.card / "Inbox" / "Show" / "e1.mkv").exists())
        self.assertFalse((self.card / "Videos" / "Show").exists())
        # A name already there: moved under a free one, and said.
        self.assertEqual((self.card / "Inbox" / "film (2).mp4").read_bytes(), b"f" * 5000)
        self.assertEqual((self.card / "Inbox" / "film.mp4").read_bytes(), b"other")
        self.assertEqual(len(notes), 1)

    def test_move_refuses_a_folder_into_itself_and_skips_the_same_place(self):
        notes = move_items(self.ftp, [("/Videos", True)], "/Videos/Show")
        self.assertTrue((self.card / "Videos" / "Show").exists())
        self.assertIn("itself", notes[0])
        self.assertEqual(move_items(self.ftp, [("/Videos/film.mp4", False)], "/Videos"), [])
        self.assertTrue((self.card / "Videos" / "film.mp4").exists())

    def test_copy_files_and_folders(self):
        steps = []
        notes = copy_items(self.ftp, [("/Videos/Show", True)], "/Inbox", steps.append)
        self.assertEqual((self.card / "Inbox" / "Show" / "e1.mkv").read_bytes(), b"a" * 100_000)
        self.assertEqual((self.card / "Inbox" / "Show" / "e2.mkv").read_bytes(), b"b" * 10)
        self.assertTrue((self.card / "Videos" / "Show" / "e1.mkv").exists())  # The original stays.
        self.assertEqual(notes, [])
        self.assertTrue(any("e1.mkv" in s for s in steps))
        # A copy in the same folder gets a new name.
        notes = copy_items(self.ftp, [("/Videos/film.mp4", False)], "/Videos")
        self.assertEqual((self.card / "Videos" / "film (2).mp4").read_bytes(), b"f" * 5000)
        self.assertEqual(len(notes), 1)
        self.assertIn("itself", copy_items(self.ftp, [("/Videos", True)], "/Videos/Show")[0])


if __name__ == "__main__":
    unittest.main()
