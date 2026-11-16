"""Uploads to a real FTP server on this computer (needs pyftpdlib; skipped
without it)."""
import tempfile
import threading
import unittest
from pathlib import Path

from kaidrop.ftp import Choice, Connection, Status, free_name, test_connection, upload
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

    def run_upload(self, cancel=None, on_conflict=None):
        plan = build_plan([self.local / "Disco Ñ"], "/Music")
        done = []
        counts = upload(self.conn, plan, lambda *a: None, lambda i, item, status, msg: done.append((status, msg)),
                        cancel or threading.Event(), on_conflict)
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

    def test_conflict_choices(self):
        self.run_upload()
        album = self.card / "Music" / "Disco N"
        asked = []

        def answer(choice, for_all=False):
            def ask(item, remote):
                asked.append((item.local.name, remote.size))
                return choice, for_all
            return ask

        counts, _ = self.run_upload(on_conflict=answer(Choice.SKIP))
        self.assertEqual(counts[Status.SKIPPED], 2)
        self.assertEqual(sorted(asked), [("01 Canción.flac", 200_000), ("cover.jpg", 3)])

        (self.local / "Disco Ñ" / "cover.jpg").write_bytes(b"new cover")
        asked.clear()
        counts, _ = self.run_upload(on_conflict=answer(Choice.REPLACE, for_all=True))
        self.assertEqual((counts[Status.SENT], len(asked)), (2, 1))  # Asked once, for all.
        self.assertEqual((album / "cover.jpg").read_bytes(), b"new cover")

        counts, done = self.run_upload(on_conflict=answer(Choice.KEEP_BOTH, for_all=True))
        self.assertEqual(counts[Status.COPY], 2)
        self.assertIn((Status.COPY, "/Music/Disco N/cover (2).jpg"), done)
        self.assertEqual((album / "01 Cancion (2).flac").stat().st_size, 200_000)
        self.assertEqual((album / "cover.jpg").read_bytes(), b"new cover")  # The old one stays.

        cancel = threading.Event()
        counts, _ = self.run_upload(cancel, answer(Choice.CANCEL))
        self.assertEqual(counts[Status.CANCELLED], 2)
        self.assertTrue(cancel.is_set())

    def test_lost_connection(self):
        import queue as q

        from kaidrop import remote

        states = q.Queue()
        old, remote.KEEPALIVE_S = remote.KEEPALIVE_S, 0.2
        try:
            session = remote.RemoteSession(self.conn, lambda fn: fn(), lambda s, m: states.put(s))
            session.submit(lambda ftp: ftp.pwd(), lambda r: None, lambda m: None)
            self.assertEqual([states.get(timeout=5), states.get(timeout=5)], [remote.CONNECTING, remote.CONNECTED])
            self.server.close_all()  # OunceShell closed.
            self.assertEqual(states.get(timeout=10), remote.LOST)
            session.close()
        finally:
            remote.KEEPALIVE_S = old

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        counts, done = self.run_upload(cancel)
        self.assertEqual(counts[Status.CANCELLED], 2)
        self.assertFalse((self.card / "Music" / "Disco N" / "01 Cancion.flac").exists())


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class BrowseTest(FtpTest):
    def test_list_and_delete(self):
        from kaidrop.ftp import connect
        from kaidrop.remote import delete_tree, list_dir

        self.run_upload()
        ftp = connect(self.conn)
        try:
            entries = list_dir(ftp, "/Music")
            self.assertEqual([(e.name, e.is_dir) for e in entries], [("Disco N", True)])
            files = list_dir(ftp, "/Music/Disco N")
            self.assertEqual({e.name for e in files}, {"01 Cancion.flac", "cover.jpg"})
            self.assertEqual(next(e.size for e in files if e.name == "cover.jpg"), 3)
            delete_tree(ftp, "/Music", True)
            self.assertEqual(list_dir(ftp, "/"), [])
        finally:
            ftp.quit()

    def test_session_runs_jobs_in_order(self):
        import queue as q

        from kaidrop.remote import RemoteSession, list_dir

        results = q.Queue()
        session = RemoteSession(self.conn, lambda fn: fn())
        session.submit(lambda ftp: ftp.mkd("/A"), lambda r: results.put("made"), results.put)
        session.submit(lambda ftp: [e.name for e in list_dir(ftp, "/")], results.put, results.put)
        self.assertEqual(results.get(timeout=5), "made")
        self.assertEqual(results.get(timeout=5), ["A"])
        session.close()


class FreeNameTest(unittest.TestCase):
    def test_free_names(self):
        taken = {"/M/song (2).mp3"}
        self.assertEqual(free_name("/M/song.mp3", taken.__contains__), "/M/song (3).mp3")
        self.assertEqual(free_name("/M/README", taken.__contains__), "/M/README (2)")
        self.assertEqual(free_name("/.hidden", taken.__contains__), "/.hidden (2)")


if __name__ == "__main__":
    unittest.main()
