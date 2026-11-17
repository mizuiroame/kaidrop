"""Receiving from the server: what to download where, and the download itself.
Files arrive as "name.part" and get their name when complete, so a stopped
download never leaves a file that looks whole."""
from __future__ import annotations

import ftplib
import posixpath
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .ftp import Choice, Connection, Status, _remote_time, connect, free_name
from .remote import list_dir

BLOCK_SIZE = 64 * 1024
PART = ".part"

# Characters Windows doesn't allow in a file name, and names it reserves.
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def local_name(name: str) -> str:
    """A server's file name as this computer can save it: '?' and the like
    as '_', no trailing dots or spaces, not a reserved name such as CON."""
    clean = _BAD.sub("_", name).rstrip(" .") or "_"
    stem = clean.split(".")[0].upper()
    return "_" + clean if stem in _RESERVED else clean


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

    def walk(remote: str, local: Path) -> None:
        folders.append(local)
        for entry in list_dir(ftp, remote):
            child_remote, child_local = posixpath.join(remote, entry.name), local / local_name(entry.name)
            if entry.is_dir:
                walk(child_remote, child_local)
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

            def block(data: bytes, out) -> None:
                nonlocal got, total
                if cancel.is_set():
                    raise _Cancelled()
                out.write(data)
                got += len(data)
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
            except (OSError, ftplib.Error) as e:
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
