"""Sending and receiving through SW2Transfer's API, against a stand-in that
serves the same folder as a test FTP server (as the console's SW2Transfer and
its FTP see the same card). Needs pyftpdlib; skipped without it."""
import json
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from kaidrop import sw2
from kaidrop.download import DownloadItem, DownloadPlan, download
from kaidrop.ftp import Connection, Status, upload
from kaidrop.plan import build_plan

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    FTPServer = None

CHUNK = 64 * 1024  # Small, so a test file is many chunks.


class FakeSw2:
    """The parts of SW2Transfer's API KaiDrop uses, on a folder."""

    def __init__(self, root: Path, password: str = ""):
        self.root, self.password, self.token = root, password, "t0ken"
        self.cancel_after: int | None = None  # Answer 410 after this many PUTs (Cancel all on the console).
        self.puts, self.ranges, self.lock = 0, 0, threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, status, body=b"", headers=None):
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _json(self, status, data):
                self._send(status, json.dumps(data).encode(), {"Content-Type": "application/json"})

            def _route(self):
                url = urllib.parse.urlsplit(self.path)
                return urllib.parse.unquote(url.path), dict(urllib.parse.parse_qsl(url.query))

            def _file(self, path):
                return fake.root / path.lstrip("/")

            def _allowed(self, path):
                if not fake.password or path in ("/api/info", "/api/login"):
                    return True
                if self.headers.get("Authorization") == "Bearer " + fake.token:
                    return True
                self._json(401, {"ok": False, "error": "password required"})
                return False

            def do_GET(self):
                path, q = self._route()
                if not self._allowed(path):
                    return
                if path == "/api/info":
                    return self._json(200, {"name": "SW2Transfer", "version": "fake", "auth": bool(fake.password)})
                if path == "/api/list":
                    folder = self._file(q["path"])
                    return self._json(200, {"ok": True, "entries": [
                        {"name": p.name, "dir": p.is_dir(), "size": p.stat().st_size} for p in folder.iterdir()]})
                if path.startswith("/dl/"):
                    f = self._file(path[3:])
                    if not f.is_file():
                        return self._json(404, {"ok": False, "error": "not found"})
                    data = f.read_bytes()
                    rng = self.headers.get("Range")
                    if self.command == "HEAD":
                        return self._head(len(data))
                    if rng:
                        a, b = (int(x) for x in rng.split("=")[1].split("-"))
                        with fake.lock:
                            fake.ranges += 1
                        return self._send(206, data[a:b + 1])
                    return self._send(200, data)
                self._json(404, {"ok": False})

            def _head(self, size):
                self.send_response(200)
                self.send_header("Content-Length", str(size))
                self.end_headers()

            def do_HEAD(self):
                self.do_GET()

            def do_POST(self):
                path, q = self._route()
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if path == "/api/login":
                    typed = urllib.parse.unquote(self.headers.get("X-SW2-Password", ""))
                    if typed == fake.password:
                        return self._json(200, {"ok": True, "token": fake.token})
                    return self._json(401, {"ok": False, "error": "wrong password"})
                if not self._allowed(path):
                    return
                if path == "/api/create":
                    f = self._file(q["path"])
                    with f.open("wb") as out:
                        out.truncate(int(q["size"]))
                    return self._json(200, {"ok": True})
                if path == "/api/delete":
                    f = self._file(q["path"])
                    if not f.exists():
                        return self._json(404, {"ok": False, "error": "not found"})
                    f.unlink()
                    return self._json(200, {"ok": True})
                if path == "/api/rename":
                    a, b = self._file(q["from"]), self._file(q["to"])
                    if b.exists():
                        return self._json(409, {"ok": False, "error": "exists"})
                    a.rename(b)
                    return self._json(200, {"ok": True})
                self._json(404, {"ok": False})

            def do_PUT(self):
                path, q = self._route()
                data = self.rfile.read(int(self.headers["Content-Length"]))
                if not self._allowed(path):
                    return
                with fake.lock:
                    fake.puts += 1
                    if fake.cancel_after is not None and fake.puts > fake.cancel_after:
                        return self._json(410, {"ok": False, "error": "cancelled"})
                f = self._file(path[3:])
                if "offset" not in q:
                    f.write_bytes(data)
                else:
                    with fake.lock, f.open("r+b") as out:
                        out.seek(int(q["offset"]))
                        out.write(data)
                self._json(200, {"ok": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class Sw2Test(unittest.TestCase):
    def setUp(self):
        sw2._absent.clear()
        self.patch = mock.patch.object(sw2, "CHUNK", CHUNK)
        self.patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.local = Path(self.tmp.name) / "local"
        self.card = Path(self.tmp.name) / "card"
        (self.local / "Album").mkdir(parents=True)
        (self.card / "switch").mkdir(parents=True)
        self.big = bytes(range(256)) * 2000 + b"end"  # 512,003 bytes: 8 chunks and a bit.
        (self.local / "Album" / "big.flac").write_bytes(self.big)
        (self.local / "Album" / "small.txt").write_bytes(b"small")
        authorizer = DummyAuthorizer()
        authorizer.add_user("kai", "pw", str(self.card), perm="elradfmwMT")
        authorizer.add_anonymous(str(self.card), perm="elradfmwMT")
        self.ftp = FTPServer(("127.0.0.1", 0), type("H", (FTPHandler,), {"authorizer": authorizer}))
        threading.Thread(target=self.ftp.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
        self.fake = FakeSw2(self.card)
        self.notes = []

    def tearDown(self):
        self.fake.close()
        self.ftp.close_all()
        self.patch.stop()
        self.tmp.cleanup()

    def conn(self, user="anonymous", password="", sw2_port=None):
        return Connection("127.0.0.1", self.ftp.address[1], user, password,
                          sw2_port=self.fake.port if sw2_port is None else sw2_port)

    def send(self, conn=None, cancel=None):
        plan = build_plan([self.local / "Album"], "/switch")
        done = []
        counts = upload(conn or self.conn(), plan, lambda *a: None, lambda i, item, st, msg: done.append(st),
                        cancel or threading.Event(), None, self.notes.append)
        return counts, done

    def test_sent_through_sw2_in_chunks(self):
        counts, _ = self.send()
        self.assertEqual(counts[Status.SENT], 2)
        self.assertEqual((self.card / "switch" / "Album" / "big.flac").read_bytes(), self.big)
        self.assertEqual((self.card / "switch" / "Album" / "small.txt").read_bytes(), b"small")
        self.assertEqual(self.fake.puts, 8 + 1)  # The big file in 8 chunks, the small one whole.
        self.assertFalse(list(self.card.rglob("*.part")))
        self.assertTrue(any("SW2Transfer fake found" in n for n in self.notes), self.notes)
        counts, _ = self.send()  # Already there, same size: skipped (asked over FTP).
        self.assertEqual(counts[Status.SKIPPED], 2)

    def test_replacing_a_file(self):
        target = self.card / "switch" / "Album" / "big.flac"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old and different")
        counts, _ = self.send()
        self.assertEqual(counts[Status.SENT], 2)
        self.assertEqual(target.read_bytes(), self.big)  # SW2Transfer's rename never replaces: deleted first.

    def test_ftp_alone_when_sw2_isnt_there_or_sees_another_card(self):
        counts, _ = self.send(self.conn(sw2_port=0))
        self.assertEqual((counts[Status.SENT], self.fake.puts), (2, 0))
        (self.card / "only on ftp").mkdir()
        other = FakeSw2(Path(self.tmp.name) / "local")  # Another folder: not the same card.
        try:
            for f in (self.card / "switch").rglob("*"):
                if f.is_file():
                    f.unlink()
            counts, _ = self.send(self.conn(sw2_port=other.port))
            self.assertEqual((counts[Status.SENT], other.puts), (2, 0))
            self.assertTrue(any("doesn't show the same folders" in n for n in self.notes), self.notes)
        finally:
            other.close()

    def test_password(self):
        self.fake.password = "pw"
        counts, _ = self.send(self.conn("kai", "pw"))
        self.assertEqual(counts[Status.SENT], 2)
        self.assertGreater(self.fake.puts, 0)
        for f in (self.card / "switch").rglob("*"):
            if f.is_file():
                f.unlink()
        self.fake.password, self.fake.puts = "another", 0
        counts, _ = self.send(self.conn("kai", "pw"))  # Wrong for SW2Transfer: FTP carries it.
        self.assertEqual((counts[Status.SENT], self.fake.puts), (2, 0))
        self.assertTrue(any("password is wrong" in n for n in self.notes), self.notes)

    def test_cancel_all_on_the_console(self):
        self.fake.cancel_after = 3
        counts, done = self.send()
        self.assertEqual(counts[Status.SENT], 0)
        self.assertEqual(counts[Status.CANCELLED], 2)  # The rest of the batch stops too.
        self.assertFalse((self.card / "switch" / "Album" / "big.flac").exists())
        self.assertFalse(list(self.card.rglob("*.part")))  # Its part removed.

    def test_received_through_sw2(self):
        album = self.card / "switch" / "Album"
        album.mkdir(parents=True)
        (album / "big.flac").write_bytes(self.big)
        here = Path(self.tmp.name) / "here"
        here.mkdir()
        plan = DownloadPlan((DownloadItem("/switch/Album/big.flac", here / "big.flac", len(self.big)),), ())
        counts = download(self.conn(), plan, lambda *a: None, lambda *a: None, threading.Event(), None,
                          self.notes.append)
        self.assertEqual(counts[Status.SENT], 1)
        self.assertEqual((here / "big.flac").read_bytes(), self.big)
        self.assertEqual(self.fake.ranges, 8)
        self.assertEqual(list(here.iterdir()), [here / "big.flac"])  # No part left.

    def test_console_closed_mid_file(self):
        """SW2Transfer and the FTP server closed while a file comes: the real
        reason ends the batch, not an error from closing a dead connection."""
        album = self.card / "switch" / "Album"
        album.mkdir(parents=True)
        (album / "big.flac").write_bytes(self.big)
        here = Path(self.tmp.name) / "here"
        here.mkdir()
        plan = DownloadPlan((DownloadItem("/switch/Album/big.flac", here / "big.flac", len(self.big)),), ())

        def gone(*args):
            self.ftp.close_all()
            raise sw2.Sw2Error("SW2Transfer stopped answering: was it closed on the console?")

        done = []
        with mock.patch.object(sw2.Sw2Client, "download", gone):
            with self.assertRaises(OSError):  # Reconnecting to FTP fails: the batch stops, to continue later.
                download(self.conn(), plan, lambda *a: None, lambda i, item, st, msg: done.append((st, msg)),
                         threading.Event())
        self.assertEqual(done[0][0], Status.FAILED)
        self.assertIn("closed on the console", done[0][1])
        self.assertEqual(list(here.iterdir()), [])

    def test_received_more_than_listed_is_refused(self):
        album = self.card / "switch" / "Album"
        album.mkdir(parents=True)
        (album / "big.flac").write_bytes(self.big)
        here = Path(self.tmp.name) / "here"
        here.mkdir()
        plan = DownloadPlan((DownloadItem("/switch/Album/big.flac", here / "big.flac", 10),), ())
        with mock.patch("kaidrop.download.SIZE_SLACK", 1000):  # The listing said 10 bytes; 512,003 come.
            counts = download(self.conn(), plan, lambda *a: None, lambda *a: None, threading.Event())
        self.assertEqual(counts[Status.FAILED], 1)
        self.assertEqual(list(here.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
