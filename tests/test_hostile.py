"""What a hostile FTP server could send: names that climb out of a folder,
listings that loop, and more bytes than it promised. Uses a fake server."""
import ftplib
import tempfile
import threading
import unittest
from pathlib import Path

from kaidrop.download import DownloadItem, DownloadPlan, local_name, plan_download, runs_code
from kaidrop.remote import MAX_DEPTH, TooDeep, delete_tree, list_dir, usable_name


class FakeFtp:
    """Answers MLSD from a dict {path: [(name, type, size)]}; a missing path
    answers with one folder "deeper", for a tree with no end."""

    def __init__(self, tree, endless=False):
        self.tree, self.endless, self.deleted = tree, endless, []

    def mlsd(self, path, facts=None):
        if self.endless:
            return iter([("deeper", {"type": "dir"})])
        return iter([(name, {"type": kind, "size": str(size)}) for name, kind, size in self.tree.get(path, [])])

    def rmd(self, path):
        self.deleted.append(path)

    def delete(self, path):
        self.deleted.append(path)


class NamesTest(unittest.TestCase):
    def test_entries_that_would_climb_are_dropped(self):
        for bad in ("", ".", "..", "a/b", "..\\x", "/abs"):
            self.assertFalse(usable_name(bad), bad)
        self.assertTrue(usable_name("Song.mp3") and usable_name("..hidden"))
        ftp = FakeFtp({"/m": [(".", "dir", 0), ("..", "dir", 0), ("a/../../x", "file", 1), ("ok.mp3", "file", 3)]})
        self.assertEqual([e.name for e in list_dir(ftp, "/m")], ["ok.mp3"])

    def test_windows_names_that_lose_data(self):
        self.assertEqual(local_name("CON .txt"), "_CON .txt")
        self.assertEqual(local_name("COM¹"), "_COM¹")
        self.assertEqual(local_name("LPT².log"), "_LPT².log")
        self.assertEqual(local_name("bill‮gpj.exe"), "billgpj.exe")  # No text turned around.

    def test_programs_are_told_apart(self):
        for name in ("setup.exe", "invoice.PDF.scr", "run.bat", "x.lnk", "a.hta", "s.ps1"):
            self.assertTrue(runs_code(name), name)
        for name in ("song.mp3", "cover.jpg", "notes.txt", "exe", "README"):
            self.assertFalse(runs_code(name), name)

    def test_own_part_ending_is_renamed(self):
        self.assertEqual(local_name("x.kaidrop-part"), "x_kaidrop-part")
        self.assertEqual(local_name("x.part"), "x.part")  # The user's own .part files are just files.

    def test_names_that_meet_on_windows_stay_apart(self):
        ftp = FakeFtp({"/m": [("a?", "file", 1), ("a_", "file", 2), ("A_", "file", 3), ("Song.mp3", "file", 4)]})
        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_download(ftp, [("/m", True)], Path(tmp))
            names = sorted(item.local.name for item in plan.items)
        self.assertEqual(len(set(n.lower() for n in names)), 4, names)
        self.assertIn("Song.mp3", names)


class LoopTest(unittest.TestCase):
    def test_endless_tree_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(TooDeep):
                plan_download(FakeFtp({}, endless=True), [("/m", True)], Path(tmp))

    def test_delete_never_climbs_or_loops(self):
        ftp = FakeFtp({"/m": [("..", "dir", 0), ("song.mp3", "file", 1)]})
        delete_tree(ftp, "/m", True)
        self.assertEqual(ftp.deleted, ["/m/song.mp3", "/m"])
        with self.assertRaises(TooDeep):
            delete_tree(FakeFtp({}, endless=True), "/m", True)
        self.assertTrue(issubclass(TooDeep, ftplib.Error))  # Caught where other FTP errors are.
        self.assertGreater(MAX_DEPTH, 8)


try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    FTPServer = None


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class TooMuchDataTest(unittest.TestCase):
    def test_more_than_the_size_said_is_stopped(self):
        from kaidrop.download import SIZE_SLACK, download
        from kaidrop.ftp import Connection, Status

        with tempfile.TemporaryDirectory() as tmp:
            card, here = Path(tmp) / "card", Path(tmp) / "here"
            card.mkdir()
            here.mkdir()
            (card / "big.bin").write_bytes(b"b" * (SIZE_SLACK + 200_000))
            authorizer = DummyAuthorizer()
            authorizer.add_anonymous(str(card), perm="elr")
            server = FTPServer(("127.0.0.1", 0), type("H", (FTPHandler,), {"authorizer": authorizer}))
            threading.Thread(target=server.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
            try:
                plan = DownloadPlan((DownloadItem("/big.bin", here / "big.bin", 10),), ())
                done = []
                counts = download(Connection("127.0.0.1", server.address[1]), plan, lambda *a: None,
                                  lambda i, item, st, msg: done.append(st), threading.Event())
            finally:
                server.close_all()
            self.assertEqual(counts[Status.FAILED], 1)
            self.assertEqual(list(here.iterdir()), [])  # No file, and no part left behind.


if __name__ == "__main__":
    unittest.main()
