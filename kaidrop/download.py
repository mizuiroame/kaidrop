"""Receiving from the server: what to download where, and the download itself.
Files arrive as "name.kaidrop-part" and get their name when complete, so a stopped
download never leaves a file that looks whole."""
from __future__ import annotations

import ftplib
import posixpath
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .ftp import Choice, Connection, Status, _remote_time, connect, free_name
from .remote import check_depth, list_dir

BLOCK_SIZE = 64 * 1024
# Its own ending, so a download never writes over a ".part" file of the user's.
PART = ".kaidrop-part"
# A server that sends more than it said it would is stopped this far past the size.
SIZE_SLACK = 1024 * 1024
# A file of unknown size stops when the disk gets this low, so it can't fill the disk.
MIN_FREE_BYTES = 1024 ** 3
FREE_CHECK_BYTES = 64 * 1024 * 1024  # How often (in bytes received) free space is looked at.

# Characters Windows doesn't allow in a file name, and names it reserves.
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Characters that turn text around ("song‮exe.mp3" shows as "song3pm.exe"): dropped.
_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
_DIGITS = [str(i) for i in range(1, 10)] + ["¹", "²", "³"]  # Windows also reserves COM¹.
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{d}" for d in _DIGITS), *(f"LPT{d}" for d in _DIGITS)}


def local_name(name: str) -> str:
    """A server's file name as this computer can save it: '?' and the like
    as '_', no trailing dots or spaces, not a reserved name such as CON,
    and never ending in KaiDrop's own ".kaidrop-part"."""
    clean = _BAD.sub("_", _BIDI.sub("", name)).rstrip(" .") or "_"
    stem = clean.split(".")[0].rstrip(" ").upper()
    if stem in _RESERVED:
        clean = "_" + clean
    if clean.lower().endswith(PART):
        clean = clean[: -len(PART)] + "_" + PART[1:]
    return clean


# Windows runs these when they are opened, instead of showing them.
_RUNS_CODE = {
    "exe", "com", "scr", "pif", "bat", "cmd", "ps1", "psm1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "hta",
    "msi", "msp", "lnk", "url", "reg", "cpl", "jar", "py", "pyw", "appref-ms", "application", "msc", "inf",
}


def runs_code(name: str) -> bool:
    """True when opening a file of this name runs it (a program, script or shortcut)."""
    stem, dot, ext = name.rstrip(" .").rpartition(".")
    return bool(dot) and ext.lower() in _RUNS_CODE


def _unique(name: str, taken: set[str]) -> str:
    """name, or "name (2)"… if another entry of the same folder already took
    it here (Windows ignores case, and "a?" and "a_" both become "a_")."""
    if name.lower() in taken:
        name = free_name(name, lambda n: n.lower() in taken)
    taken.add(name.lower())
    return name


@dataclass(frozen=True)
class DownloadItem:
    remote: str     # Full path on the server.
    local: Path     # Where it goes here.
    size: int


@dataclass(frozen=True)
class DownloadPlan:
    items: tuple[DownloadItem, ...]
    folders: tuple[Path, ...]  # Local folders to make, parents first.

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.items)


def plan_download(ftp: ftplib.FTP, sources: list[tuple[str, bool]], local_root: Path) -> DownloadPlan:
    """Lists what each source (a server path, and whether it's a folder) holds,
    with where each file goes under local_root, keeping the folders."""
    items: list[DownloadItem] = []
    folders: list[Path] = []

    def walk(remote: str, local: Path, depth: int = 0) -> None:
        check_depth(depth)
        folders.append(local)
        taken: set[str] = set()
        for entry in list_dir(ftp, remote):
            child_remote = posixpath.join(remote, entry.name)
            child_local = local / _unique(local_name(entry.name), taken)
            if entry.is_dir:
                walk(child_remote, child_local, depth + 1)
            else:
                items.append(DownloadItem(child_remote, child_local, entry.size))

    for remote, is_dir in sources:
        target = local_root / local_name(posixpath.basename(remote.rstrip("/")))
        if is_dir:
            walk(remote, target)
        else:
            size = 0
            try:
                ftp.voidcmd("TYPE I")  # Listing left it in ASCII, where servers refuse SIZE.
                size = ftp.size(remote) or 0
            except ftplib.all_errors:
                pass
            items.append(DownloadItem(remote, target, size))
    return DownloadPlan(tuple(items), tuple(dict.fromkeys(folders)))


@dataclass(frozen=True)
class LocalFile:
    path: Path
    size: int
    modified: datetime | None


ProgressFn = Callable[[int, DownloadItem, int, int], None]  # index, item, item bytes, total bytes
DoneFn = Callable[[int, DownloadItem, Status, str], None]   # index, item, status, message (the new path for a copy)
ConflictFn = Callable[[DownloadItem, LocalFile, "datetime | None"], "tuple[Choice, bool]"]  # item, the file here, server time


def _free_local(path: Path) -> Path:
    return Path(free_name(path.as_posix(), lambda p: Path(p).exists()))


def _drop(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def download(conn: Connection, plan: DownloadPlan, on_progress: ProgressFn, on_done: DoneFn,
             cancel: threading.Event, on_conflict: ConflictFn | None = None) -> dict[Status, int]:
    """Downloads every item, reporting progress; returns how many ended in
    each status. For a file already here, on_conflict says what to do;
    without it, one with the same size is skipped and others replaced."""
    counts = {status: 0 for status in Status}
    ftp = connect(conn)
    total = 0
    for_all: Choice | None = None
    try:
        for folder in plan.folders:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # Its files fail below, with the reason.
        for index, item in enumerate(plan.items):
            if cancel.is_set():
                on_done(index, item, Status.CANCELLED, "")
                counts[Status.CANCELLED] += 1
                continue
            target, status = item.local, Status.SENT
            if target.exists():
                stat = target.stat()
                here = LocalFile(target, stat.st_size, datetime.fromtimestamp(stat.st_mtime))
                if for_all:
                    choice = for_all
                elif on_conflict:
                    choice, remember = on_conflict(item, here, _remote_time(ftp, item.remote))
                    for_all = choice if remember else None
                else:
                    choice = Choice.SKIP if here.size == item.size else Choice.REPLACE
                if choice is Choice.CANCEL:
                    cancel.set()
                    on_done(index, item, Status.CANCELLED, "")
                    counts[Status.CANCELLED] += 1
                    continue
                if choice is Choice.SKIP:  # Done first, so the progress jump isn't taken for speed.
                    total += item.size
                    on_done(index, item, Status.SKIPPED, "")
                    on_progress(index, item, item.size, total)
                    counts[Status.SKIPPED] += 1
                    continue
                if choice is Choice.KEEP_BOTH:
                    target, status = _free_local(target), Status.COPY
            part = target.with_name(target.name + PART)
            got = 0
            next_free_check = FREE_CHECK_BYTES

            def block(data: bytes, out) -> None:
                nonlocal got, total, next_free_check
                if cancel.is_set():
                    raise _Cancelled()
                got += len(data)
                if item.size and got > item.size + SIZE_SLACK:
                    raise OSError("The server sent more than the file's size.")
                if not item.size and got >= next_free_check:
                    next_free_check += FREE_CHECK_BYTES
                    if shutil.disk_usage(part.parent).free < MIN_FREE_BYTES:
                        raise OSError("The disk is nearly full.")
                out.write(data)
                total += len(data)
                on_progress(index, item, got, total)

            try:
                with part.open("wb") as out:
                    ftp.retrbinary(f"RETR {item.remote}", lambda d, o=out: block(d, o), BLOCK_SIZE)
                part.replace(target)
                on_done(index, item, status, str(target) if status is Status.COPY else "")
                counts[status] += 1
            except _Cancelled:
                _drop(part)
                ftp = _fresh(conn, ftp)
                on_done(index, item, Status.CANCELLED, "")
                counts[Status.CANCELLED] += 1
            except (OSError, EOFError, ftplib.Error) as e:  # EOFError: the server closed mid-file.
                _drop(part)
                on_done(index, item, Status.FAILED, str(e))
                counts[Status.FAILED] += 1
                ftp = _fresh(conn, ftp)
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()
    return counts


class _Cancelled(Exception):
    pass


def _fresh(conn: Connection, ftp: ftplib.FTP) -> ftplib.FTP:
    """After a stopped transfer the control connection may be unusable: a new one."""
    try:
        ftp.close()
    except ftplib.all_errors:
        pass
    return connect(conn)
