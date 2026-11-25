"""Playlists that keep working after renaming.

A playlist (.m3u, .m3u8 or .pls) lists songs by path. When KaiDrop gives
the songs, or the folders above them, plain names on the console, the copy
of the playlist that goes there is rewritten to point to those names. The
file on the computer is never changed.

- A relative entry is resolved against the playlist's folder on this
  computer and mapped through the names KaiDrop gives that file and the
  folders on its way.
- An absolute entry (C:\\Music\\song.flac, file:///...) is rewritten only
  when its song is in the same transfer; others are left as they were.
- Comment lines (#EXTM3U, #EXTINF...), line endings and the encoding are
  kept: .m3u8 is UTF-8, .m3u and .pls the system code page (UTF-8 if
  they have a BOM, or their accents are only valid as UTF-8).
  Rewritten paths use forward slashes, relative to the playlist.
"""
from __future__ import annotations

import locale
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from .names import unique_names

EXTENSIONS = (".m3u", ".m3u8", ".pls")
MAX_BYTES = 4 << 20  # Bigger ones aren't playlists anyone wrote by hand: sent as they are.
BOM = b"\xef\xbb\xbf"
_PLS_ENTRY = re.compile(r"^(\s*File\d+\s*=\s*)(.*?)\s*$", re.IGNORECASE)
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class Change:
    """A line that points to a song's name on the console."""
    index: int      # The line, counting from 0.
    line: bytes     # The rewritten line, with its ending.
    remote: str     # The song's full path on the console.
    sent: bool      # The song is in the same transfer: no need to ask the server.


@dataclass(frozen=True)
class PlaylistCopy:
    """A playlist's copy for the console: its lines and the ones to change."""
    lines: tuple[bytes, ...]
    bom: bytes
    changes: tuple[Change, ...]
    outside: int    # Absolute entries whose song isn't being sent: left as they were.

    def render(self, on_server: Callable[[str], bool]) -> tuple[bytes, int, int]:
        """The bytes to send, how many entries were changed, and how many were
        left because their song wasn't sent and isn't on the server either."""
        lines = list(self.lines)
        changed = 0
        for change in self.changes:
            if change.sent or on_server(change.remote):
                lines[change.index] = change.line
                changed += 1
        return self.bom + b"".join(lines), changed, len(self.changes) - changed

    @property
    def size(self) -> int:
        """The size with every change made (as planned)."""
        return len(self.render(lambda _: True)[0])


def is_playlist(path: Path) -> bool:
    return path.suffix.lower() in EXTENSIONS


def _encoding(path: Path, data: bytes, has_bom: bool) -> str:
    if has_bom or path.suffix.lower() == ".m3u8":
        return "utf-8"
    try:  # Accents in the code page are hardly ever valid UTF-8: one that is was written as UTF-8.
        if not data.isascii():
            data.decode("utf-8")
            return "utf-8"
    except UnicodeDecodeError:
        pass
    getencoding = getattr(locale, "getencoding", None)  # Python 3.11+.
    return getencoding() if getencoding else locale.getpreferredencoding(False)


def local_key(path: str | Path) -> str:
    """Compares paths as Windows does: case and slashes don't matter."""
    return os.path.normcase(os.path.abspath(path))


def _local_target(entry: str, folder: Path) -> tuple[Path | None, bool]:
    """The file an entry names on this computer, and whether it was absolute.
    None for what isn't a file path (http://... and the like)."""
    if entry.lower().startswith("file:"):
        url = urlparse(entry)
        path = unquote(url.path)
        if url.netloc and url.netloc.lower() != "localhost":
            path = f"//{url.netloc}{path}"  # A network share.
        elif re.match(r"^/[A-Za-z]:", path):
            path = path[1:]  # "/C:/Music" is "C:/Music".
        return Path(path), True
    if "://" in entry:
        return None, False
    entry = entry.replace("\\", "/")
    if _DRIVE.match(entry) or entry.startswith("//"):
        return Path(entry), True
    if entry.startswith("/"):
        return Path(folder.drive + entry), True  # On the playlist's drive.
    return Path(os.path.abspath(folder / entry)), False


class _Names:
    """The names the files in a local folder get on the console, as plan.py
    gives them, looked up without regard to case."""

    def __init__(self, plain: bool) -> None:
        self.plain = plain
        self.folders: dict[str, dict[str, str]] = {}

    def get(self, folder: Path, name: str) -> str | None:
        key = local_key(folder)
        if key not in self.folders:
            try:
                entries = list(folder.iterdir())
            except OSError:
                entries = []
            names = unique_names([e.name for e in entries], {e.name for e in entries if e.is_dir()}, self.plain,
                                 str(folder))
            self.folders[key] = {local.lower(): remote for local, remote in names.items()}
        return self.folders[key].get(name.lower())


def _console_relative(song: Path, folder: Path, names: _Names) -> str | None:
    """The path from the playlist to a song not in this transfer, with the
    names KaiDrop gives it on the console. None if the song isn't there."""
    try:
        parts = Path(os.path.relpath(song, folder)).parts
    except ValueError:
        return None  # Another drive.
    ups = 0
    while ups < len(parts) and parts[ups] == "..":
        ups += 1
    where = Path(os.path.abspath(folder))
    for _ in range(ups):
        where = where.parent
    out = [".."] * ups
    for part in parts[ups:]:
        console = names.get(where, part)
        if console is None:
            return None
        out.append(console)
        where = where / part
    return "/".join(out) if len(out) > ups else None


def _climb(folder: str, relative: str) -> str | None:
    """The console path a relative entry resolves to, as KaiPlayer resolves it
    (None if it goes above the root)."""
    parts = [p for p in folder.split("/") if p]
    for part in relative.split("/"):
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/" + "/".join(parts)


def _same(a: str, b: str) -> bool:
    return posixpath.normpath(a.replace("\\", "/")) == posixpath.normpath(b)


def prepare(local: Path, remote: str, sent: dict[str, str], plain: bool = True) -> PlaylistCopy | None:
    """Works out the console copy of the playlist at local, going to remote.
    sent maps each file in the transfer (by local_key) to its path on the console.
    None when nothing in it needs changing, or it can't be read."""
    try:
        if local.stat().st_size > MAX_BYTES:
            return None
        data = local.read_bytes()
    except OSError:
        return None
    bom = BOM if data.startswith(BOM) else b""
    data = data[len(bom):]
    encoding = _encoding(local, data, bool(bom))
    folder, remote_folder = local.parent, posixpath.dirname(remote) or "/"
    names = _Names(plain)
    lines = tuple(data.splitlines(keepends=True))
    changes: list[Change] = []
    outside = 0
    for index, raw in enumerate(lines):
        body = raw.rstrip(b"\r\n")
        try:
            text = body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue  # Left as it is.
        prefix, entry = "", text.strip()
        if local.suffix.lower() == ".pls":
            match = _PLS_ENTRY.match(text)
            if not match:
                continue
            prefix, entry = match.group(1), match.group(2)
        elif not entry or entry.startswith("#"):
            continue
        song, absolute = _local_target(entry, folder)
        if song is None:
            continue
        in_transfer = sent.get(local_key(song))
        if in_transfer:
            new, target = posixpath.relpath(in_transfer, remote_folder), in_transfer
        elif absolute:
            outside += 1
            continue
        else:
            new = _console_relative(song, folder, names)
            target = _climb(remote_folder, new) if new else None
            if not new or not target:
                continue
        if _same(entry, new) and not absolute:
            continue
        try:
            line = (prefix + new).encode(encoding) + raw[len(body):]
        except UnicodeEncodeError:
            continue
        changes.append(Change(index, line, target, bool(in_transfer)))
    if not changes and not outside:
        return None
    return PlaylistCopy(lines, bom, tuple(changes), outside)


def describe(name: str, changed: int, missing: int, outside: int) -> str:
    """The log line after sending a playlist."""
    def entries(n: int, one: str, many: str) -> str:
        return f"{n} {'entry' if n == 1 else 'entries'} {one if n == 1 else many}"

    text = f"Playlist {name}: {entries(changed, 'points', 'point')} to the names on the console"
    if missing:
        text += f", {missing} left as {'it was' if missing == 1 else 'they were'} (the song isn't on the console)"
    if outside:
        text += f", {entries(outside, 'points', 'point')} outside what was sent (left as they were)"
    return text + "."
