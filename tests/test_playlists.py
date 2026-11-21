"""Playlists whose copy on the console points to the songs' plain names."""
import locale
import tempfile
import threading
import unittest
from pathlib import Path

from kaidrop.ftp import Connection, Status, upload
from kaidrop.plan import build_plan
from kaidrop.playlists import describe

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    FTPServer = None


# --- KaiPlayer's playlist reading (source/playlist.c and util.c), ported ---

def _device_prefix(path: str) -> int:
    colon = path.find(":/")
    return colon + 2 if colon >= 0 and "/" not in path[:colon] else 0


def _normalize(path: str) -> str | None:
    prefix = _device_prefix(path) or (1 if path.startswith("/") else 0)
    parts: list[str] = []
    for part in path[prefix:].split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return path[:prefix] + "/".join(parts)


def _resolve(base_dir: str, ref: str) -> str | None:
    clean = ref.replace("\\", "/")
    if _device_prefix(clean):
        joined = clean
    elif clean.startswith("/"):
        prefix = _device_prefix(base_dir)
        joined = base_dir[:prefix - 1 if prefix else 0] + clean
    else:
        joined = base_dir + ("" if base_dir.endswith("/") else "/") + clean
    return _normalize(joined)


def kaiplayer_parse(data: bytes, base_dir: str) -> list[str]:
    """The songs KaiPlayer finds in a playlist file in base_dir."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    songs = []
    for raw in data.split(b"\n"):
        line = raw.rstrip(b"\r \t").lstrip(b" \t")
        if line and not line.startswith(b"#"):
            path = _resolve(base_dir, line.decode("utf-8", "replace"))
            if path:
                songs.append(path)
    return songs


def everything_there(path: str) -> bool:
    return True


class Library(unittest.TestCase):
    """A music folder with accents and Japanese, and a Playlists folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / "Música"
        artist = root / "Artista Ñ"
        (artist / "Disco Ü").mkdir(parents=True)
        (root / "松原みき").mkdir()
        (root / "Playlists").mkdir()
        (artist / "06 Canción.flac").write_bytes(b"a")
        (artist / "07 Plain.flac").write_bytes(b"b")
        (artist / "Disco Ü" / "01 Ñu.flac").write_bytes(b"c")
        (root / "松原みき" / "04 みずいろの雨.mp3").write_bytes(b"d")
        (root / "Top.mp3").write_bytes(b"e")
        self.outside = Path(self.tmp.name) / "Elsewhere" / "lejos.mp3"
        self.outside.parent.mkdir()
        self.outside.write_bytes(b"f")
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str, encoding: str = "utf-8", newline: str = "\n", bom: bool = False) -> Path:
        path = self.root / "Playlists" / name
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.replace("\n", newline).encode(encoding))
        return path

    def item(self, plan, name: str):
        return next(item for item in plan.items if item.local.name == name)

    def send_all(self):
        """The whole music folder, songs and playlists together, into /music."""
        return build_plan([self.root], "/music")


class PlaylistTest(Library):
    def test_relative_entries_sent_together(self):
        self.write("mix.m3u8", "#EXTM3U\n#EXTINF:201,Artista - Canción\n../Artista Ñ/06 Canción.flac\n"
                   "../Artista Ñ/07 Plain.flac\n../Top.mp3\n")
        item = self.item(self.send_all(), "mix.m3u8")
        self.assertEqual(item.remote, "/music/Musica/Playlists/mix.m3u8")
        self.assertEqual(item.playlist_changes, 2)  # Top.mp3 keeps its name.
        data, changed, missing = item.playlist.render(lambda p: self.fail("songs being sent aren't looked up"))
        self.assertEqual(data.decode("utf-8"), "#EXTM3U\n#EXTINF:201,Artista - Canción\n../Artista N/06 Cancion.flac\n"
                         "../Artista N/07 Plain.flac\n../Top.mp3\n")
        self.assertEqual((changed, missing), (2, 0))
        self.assertEqual(item.size, len(data))

    def test_nested_folders_renamed_and_backslashes(self):
        self.write("deep.m3u", "..\\Artista Ñ\\Disco Ü\\01 Ñu.flac\n", "utf-8", bom=True)
        data, _, _ = self.item(self.send_all(), "deep.m3u").playlist.render(everything_there)
        self.assertEqual(data, b"\xef\xbb\xbf../Artista N/Disco U/01 Nu.flac\n")

    def test_japanese_names(self):
        self.write("jp.m3u8", "#EXTINF:180,松原みき - みずいろの雨\n../松原みき/04 みずいろの雨.mp3\n")
        data, _, _ = self.item(self.send_all(), "jp.m3u8").playlist.render(everything_there)
        self.assertEqual(data.decode("utf-8"), "#EXTINF:180,松原みき - みずいろの雨\n../untitled/04 _.mp3\n")

    def test_absolute_inside_and_outside(self):
        song = self.root / "Artista Ñ" / "06 Canción.flac"
        self.write("abs.m3u8", f"#EXTM3U\n{song}\n{(self.root / 'Top.mp3').as_uri()}\n{self.outside}\n"
                   f"{self.outside.as_uri()}\nhttp://radio.example/stream\n")
        item = self.item(self.send_all(), "abs.m3u8")
        data, changed, missing = item.playlist.render(everything_there)
        self.assertEqual(data.decode("utf-8").splitlines(), [
            "#EXTM3U", "../Artista N/06 Cancion.flac", "../Top.mp3", str(self.outside), self.outside.as_uri(),
            "http://radio.example/stream"])
        self.assertEqual((changed, item.playlist.outside), (2, 2))
        self.assertIn("2 entries point outside what was sent", describe("abs.m3u8", changed, missing, item.playlist.outside))

    def test_line_endings_kept(self):
        self.write("crlf.m3u8", "#EXTM3U\n../Artista Ñ/06 Canción.flac\n../Top.mp3", newline="\r\n")
        data, _, _ = self.item(self.send_all(), "crlf.m3u8").playlist.render(everything_there)
        self.assertEqual(data, b"#EXTM3U\r\n../Artista N/06 Cancion.flac\r\n../Top.mp3")

    def test_m3u_in_the_system_code_page(self):
        encoding = getattr(locale, "getencoding", lambda: locale.getpreferredencoding(False))()
        try:
            "Canción Ñ".encode(encoding)
        except UnicodeEncodeError:
            self.skipTest(f"{encoding} has no accents")
        self.write("old.m3u", "#EXTINF:1,Canción\n../Artista Ñ/06 Canción.flac\n", encoding)
        data, _, _ = self.item(self.send_all(), "old.m3u").playlist.render(everything_there)
        self.assertEqual(data, "#EXTINF:1,Canción\n../Artista N/06 Cancion.flac\n".encode(encoding))

    def test_m3u_written_as_utf8_without_a_bom(self):
        self.write("new.m3u", "#EXTINF:1,Canción\n../Artista Ñ/06 Canción.flac\n")
        data, _, _ = self.item(self.send_all(), "new.m3u").playlist.render(everything_there)
        self.assertEqual(data.decode("utf-8"), "#EXTINF:1,Canción\n../Artista N/06 Cancion.flac\n")

    def test_pls(self):
        self.write("radio.pls", "[playlist]\nFile1=../Artista Ñ/06 Canción.flac\nTitle1=Canción\nNumberOfEntries=1\n")
        data, _, _ = self.item(self.send_all(), "radio.pls").playlist.render(everything_there)
        self.assertEqual(data.decode("utf-8"),
                         "[playlist]\nFile1=../Artista N/06 Cancion.flac\nTitle1=Canción\nNumberOfEntries=1\n")

    def test_songs_already_on_the_server(self):
        # Only the playlist is sent, into the Playlists folder of the music already there.
        playlist = self.write("mix.m3u8", "#EXTM3U\n../Artista Ñ/06 Canción.flac\n../Artista Ñ/Disco Ü/01 Ñu.flac\n"
                              "../Artista Ñ/08 Missing.flac\n")
        item = build_plan([playlist], "/music/Musica/Playlists").items[0]
        on_server = {"/music/Musica/Artista N/06 Cancion.flac"}
        data, changed, missing = item.playlist.render(on_server.__contains__)
        self.assertEqual(data.decode("utf-8"), "#EXTM3U\n../Artista N/06 Cancion.flac\n../Artista Ñ/Disco Ü/01 Ñu.flac\n"
                         "../Artista Ñ/08 Missing.flac\n")  # Not on the console, or not on this computer: as it was.
        self.assertEqual((changed, missing), (1, 1))

    def test_nothing_to_change(self):
        self.write("plain.m3u8", "#EXTM3U\n../Top.mp3\n")
        self.assertIsNone(self.item(self.send_all(), "plain.m3u8").playlist)

    def test_file_on_the_computer_untouched(self):
        text = "#EXTM3U\n../Artista Ñ/06 Canción.flac\n"
        path = self.write("mix.m3u8", text)
        self.item(self.send_all(), "mix.m3u8").playlist.render(everything_there)
        self.assertEqual(path.read_bytes(), text.encode("utf-8"))

    def test_kaiplayer_reads_the_rewritten_playlist(self):
        song = self.root / "Artista Ñ" / "Disco Ü" / "01 Ñu.flac"
        self.write("Mix.m3u8", f"﻿#EXTM3U\r\n#EXTINF:1,Ñu\r\n../Artista Ñ/06 Canción.flac\r\n{song}\r\n"
                   "  ../松原みき/04 みずいろの雨.mp3  \r\n../Top.mp3\r\n")
        plan = self.send_all()
        item = self.item(plan, "Mix.m3u8")
        data, _, _ = item.playlist.render(everything_there)
        base = "sdmc:" + item.remote.rsplit("/", 1)[0]
        remote = {i.local.name: "sdmc:" + i.remote for i in plan.items}
        self.assertEqual(kaiplayer_parse(data, base), [remote["06 Canción.flac"], remote["01 Ñu.flac"],
                                                       remote["04 みずいろの雨.mp3"], remote["Top.mp3"]])


@unittest.skipIf(FTPServer is None, "pyftpdlib is not installed")
class PlaylistUploadTest(Library):
    def setUp(self):
        super().setUp()
        self.card = Path(self.tmp.name) / "card"
        self.card.mkdir()
        authorizer = DummyAuthorizer()
        authorizer.add_anonymous(str(self.card), perm="elradfmwMT")
        handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
        self.conn = Connection("127.0.0.1", self.server.address[1])

    def tearDown(self):
        self.server.close_all()
        super().tearDown()

    def send(self, plan):
        done = []
        upload(self.conn, plan, lambda *a: None, lambda i, item, s, m: done.append((item.local.name, s, m)),
               threading.Event())
        return done

    def test_sent_with_the_songs_then_alone(self):
        text = "#EXTM3U\n../Artista Ñ/06 Canción.flac\n../Artista Ñ/Disco Ü/01 Ñu.flac\n"
        playlist = self.write("mix.m3u8", text)
        self.send(self.send_all())
        on_card = self.card / "music" / "Musica" / "Playlists" / "mix.m3u8"
        expected = "#EXTM3U\n../Artista N/06 Cancion.flac\n../Artista N/Disco U/01 Nu.flac\n"
        self.assertEqual(on_card.read_text("utf-8"), expected)

        # Sent again alone, after one song went from the console: that line stays as it was.
        (self.card / "music" / "Musica" / "Artista N" / "Disco U" / "01 Nu.flac").unlink()
        on_card.unlink()
        done = self.send(build_plan([playlist], "/music/Musica/Playlists"))
        self.assertEqual(on_card.read_text("utf-8"),
                         "#EXTM3U\n../Artista N/06 Cancion.flac\n../Artista Ñ/Disco Ü/01 Ñu.flac\n")
        self.assertEqual(done[0][1], Status.SENT)
        self.assertIn("1 entry points to the names on the console, 1 left as it was", done[0][2])
        self.assertEqual(playlist.read_text("utf-8"), text)  # Never changed here.


if __name__ == "__main__":
    unittest.main()
