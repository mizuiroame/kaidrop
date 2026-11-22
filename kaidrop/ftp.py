"""Sends a plan to the console over FTP. Files arrive as "name.part" and get
their name when complete, so a lost connection never leaves a file that looks
whole (and that a later "Skip" would keep)."""
from __future__ import annotations

import ftplib
import io
import posixpath
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from . import sw2
from .plan import Plan, UploadItem
from .playlists import describe as describe_playlist

BLOCK_SIZE = 64 * 1024
PART = ".part"


class Status(Enum):
    SENT = "Sent"
    SKIPPED = "Already there"
    COPY = "Sent as a copy"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass(frozen=True)
class Connection:
    host: str
    port: int = 5000
    user: str = "anonymous"
    password: str = ""
    timeout: float = 30.0
    sw2_port: int = sw2.API_PORT  # SW2Transfer's API, used for the files' bytes when it's there; 0: FTP only.


class Cancelled(Exception):
    """The user stopped the upload."""


class Choice(Enum):
    """What to do with a file already on the server."""
    SKIP = "skip"
    REPLACE = "replace"
    KEEP_BOTH = "keep both"  # Send the new one under a free name.
    CANCEL = "cancel"        # Stop the batch.


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    modified: datetime | None  # None when the server doesn't say.


# Asked when a file is already there: the choice, and whether it goes for
# the rest of the batch too.
ConflictFn = Callable[["UploadItem", RemoteFile], "tuple[Choice, bool]"]


def connect(conn: Connection) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(conn.host, conn.port, timeout=conn.timeout)
    ftp.login(conn.user, conn.password)
    ftp.encoding = "utf-8"
    ftp.voidcmd("TYPE I")  # Binary; some servers only answer SIZE in it.
    return ftp


def test_connection(conn: Connection) -> str:
    """Connects and logs in; returns the server's welcome line."""
    ftp = connect(conn)
    try:
        return ftp.getwelcome()
    finally:
        ftp.quit()


def _remote_size(ftp: ftplib.FTP, path: str) -> int | None:
    try:
        return ftp.size(path)
    except ftplib.all_errors:
        return None


def _remote_time(ftp: ftplib.FTP, path: str) -> datetime | None:
    """The file's modification time (MDTM), in local time."""
    try:
        reply = ftp.sendcmd(f"MDTM {path}")
        stamp = datetime.strptime(reply.split()[1][:14], "%Y%m%d%H%M%S")
        return stamp.replace(tzinfo=timezone.utc).astimezone()
    except (ftplib.all_errors, ValueError, IndexError):
        return None


def free_name(path: str, taken: Callable[[str], bool]) -> str:
    """The first of "song (2).mp3", "song (3).mp3"… that isn't taken."""
    folder, name = posixpath.split(path)
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, dot, ext = name, "", ""
    n = 2
    while True:
        candidate = posixpath.join(folder, f"{stem} ({n}){dot}{ext}")
        if not taken(candidate):
            return candidate
        n += 1


def _make_folders(ftp: ftplib.FTP, folders: tuple[str, ...]) -> None:
    for folder in folders:
        current = ""
        for part in folder.strip("/").split("/"):
            current += "/" + part
            try:
                ftp.mkd(current)
            except ftplib.error_perm:
                pass  # Already there.


ProgressFn = Callable[[int, UploadItem, int, int], None]  # index, item, item bytes sent, total sent
DoneFn = Callable[[int, UploadItem, Status, str], None]   # index, item, status, message
NoteFn = Callable[[str], None]                             # A line for the log.


def fast_path(conn: Connection, ftp: ftplib.FTP, on_note: NoteFn) -> sw2.Sw2Client | None:
    """SW2Transfer's API on the same console, if it's there (see sw2.py)."""
    if not conn.sw2_port:
        return None
    return sw2.for_ftp(conn.host, conn.password, ftp, on_note, conn.sw2_port)


def upload(conn: Connection, plan: Plan, on_progress: ProgressFn, on_done: DoneFn,
           cancel: threading.Event, on_conflict: ConflictFn | None = None,
           on_note: NoteFn = lambda _: None) -> dict[Status, int]:
    """Uploads every item, reporting progress, and returns how many ended in
    each status. For a file already on the server, on_conflict says what to
    do; without it, one with the same size is skipped and others replaced.
    A file sent as a copy reports its new path as the message; a playlist
    sent, what was changed in its copy."""
    counts = {status: 0 for status in Status}
    ftp = connect(conn)
    total_sent = 0
    for_all: Choice | None = None
    fast = fast_path(conn, ftp, on_note)
    lock = threading.Lock()  # SW2Transfer's chunks report from several threads.
    try:
        _make_folders(ftp, plan.folders)
        for index, item in enumerate(plan.items):
            if cancel.is_set():
                on_done(index, item, Status.CANCELLED, "")
                counts[Status.CANCELLED] += 1
                continue
            target, status = item.remote, Status.SENT
            existing = _remote_size(ftp, item.remote)
            if existing is not None:
                if for_all:
                    choice = for_all
                elif on_conflict:
                    choice, remember = on_conflict(item, RemoteFile(item.remote, existing,
                                                                    _remote_time(ftp, item.remote)))
                    for_all = choice if remember else None
                else:
                    choice = Choice.SKIP if existing == item.size else Choice.REPLACE
                if choice is Choice.CANCEL:
                    cancel.set()
                    on_done(index, item, Status.CANCELLED, "")
                    counts[Status.CANCELLED] += 1
                    continue
                if choice is Choice.SKIP:  # Done first, so the progress jump isn't taken for speed.
                    total_sent += item.size
                    on_done(index, item, Status.SKIPPED, "")
                    on_progress(index, item, item.size, total_sent)
                    counts[Status.SKIPPED] += 1
                    continue
                if choice is Choice.KEEP_BOTH:
                    target = free_name(item.remote, lambda p: _remote_size(ftp, p) is not None)
                    status = Status.COPY
            part = target + PART
            sent = 0

            def moved(count: int) -> None:
                nonlocal sent, total_sent
                with lock:
                    sent += count
                    total_sent += count
                    on_progress(index, item, sent, total_sent)

            def block(data: bytes) -> None:
                if cancel.is_set():
                    raise Cancelled()
                moved(len(data))

            try:
                note = ""
                if fast and not item.playlist:  # SW2Transfer: the bytes over its API, in chunks at once.
                    fast.upload(item.local, part, moved, cancel)
                    _settle_sw2(fast, part, target)
                    on_done(index, item, status, target if status is Status.COPY else note)
                    counts[status] += 1
                    continue
                if item.playlist:  # Its copy points to the songs' names on the console.
                    data, changed, missing = item.playlist.render(lambda p: _remote_size(ftp, p) is not None)
                    note = describe_playlist(posixpath.basename(target), changed, missing, item.playlist.outside)
                    source = io.BytesIO(data)
                else:
                    source = item.local.open("rb")
                with source as f:
                    ftp.storbinary(f"STOR {part}", f, BLOCK_SIZE, callback=block)
                _settle(ftp, part, target)
                on_done(index, item, status, target if status is Status.COPY else note)
                counts[status] += 1
            except (Cancelled, sw2.Sw2Cancelled):
                cancel.set()  # Cancel all on the console stops the batch too.
                ftp = _drop_part(conn, ftp, fast, part)
                on_done(index, item, Status.CANCELLED, "")
                counts[Status.CANCELLED] += 1
            except (OSError, EOFError, ftplib.Error, sw2.Sw2Error) as e:  # EOFError: the server closed mid-file.
                on_done(index, item, Status.FAILED, str(e))
                counts[Status.FAILED] += 1
                ftp = _drop_part(conn, ftp, fast, part)
    finally:
        _close(ftp)
        if fast:
            fast.close()
    return counts


def _settle(ftp: ftplib.FTP, part: str, target: str) -> None:
    """Gives the complete file its name, replacing what was there (servers
    differ on renaming onto an existing file, so that goes first)."""
    try:
        ftp.delete(target)
    except ftplib.error_perm:
        pass  # Nothing there.
    ftp.rename(part, target)


def _settle_sw2(fast: sw2.Sw2Client, part: str, target: str) -> None:
    """_settle through SW2Transfer, which closes its handle on part first."""
    try:
        fast.delete(target)
    except sw2.Sw2Error:
        pass  # Nothing there.
    fast.rename(part, target)


def _drop_part(conn: Connection, ftp: ftplib.FTP, fast: sw2.Sw2Client | None, part: str) -> ftplib.FTP:
    """After a stopped file: a fresh FTP connection, and its part removed (by
    SW2Transfer when it wrote it: it closes its handle first)."""
    if fast:
        try:
            fast.delete(part)
        except sw2.Sw2Error:
            pass
    return _reconnect_and_delete(conn, ftp, part)


def _close(ftp: ftplib.FTP) -> None:
    try:
        ftp.quit()
    except (*ftplib.all_errors, AttributeError):  # AttributeError: already closed.
        ftp.close()


def _reconnect_and_delete(conn: Connection, ftp: ftplib.FTP, path: str) -> ftplib.FTP:
    """After an interrupted transfer the control connection may be unusable:
    open a fresh one and remove the partial file. If the server is gone this
    raises, and the .part stays until the next send overwrites it."""
    ftp.close()
    fresh = connect(conn)
    try:
        fresh.delete(path)
    except ftplib.all_errors:
        pass
    return fresh
