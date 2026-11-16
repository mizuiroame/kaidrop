"""Sends a plan to the console over FTP."""
from __future__ import annotations

import ftplib
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .plan import Plan, UploadItem

BLOCK_SIZE = 64 * 1024


class Status(Enum):
    SENT = "Sent"
    SKIPPED = "Already there"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass(frozen=True)
class Connection:
    host: str
    port: int = 5000
    user: str = "anonymous"
    password: str = ""
    timeout: float = 30.0


class Cancelled(Exception):
    """The user stopped the upload."""


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


def upload(conn: Connection, plan: Plan, on_progress: ProgressFn, on_done: DoneFn,
           cancel: threading.Event, skip_existing: bool = True) -> dict[Status, int]:
    """Uploads every item, reporting progress. Files already on the console
    with the same size are skipped. Returns how many ended in each status."""
    counts = {status: 0 for status in Status}
    ftp = connect(conn)
    total_sent = 0
    try:
        _make_folders(ftp, plan.folders)
        for index, item in enumerate(plan.items):
            if cancel.is_set():
                on_done(index, item, Status.CANCELLED, "")
                counts[Status.CANCELLED] += 1
                continue
            if skip_existing and _remote_size(ftp, item.remote) == item.size:
                total_sent += item.size
                on_progress(index, item, item.size, total_sent)
                on_done(index, item, Status.SKIPPED, "")
                counts[Status.SKIPPED] += 1
                continue
            sent = 0

            def block(data: bytes) -> None:
                nonlocal sent, total_sent
                if cancel.is_set():
                    raise Cancelled()
                sent += len(data)
                total_sent += len(data)
                on_progress(index, item, sent, total_sent)

            try:
                with item.local.open("rb") as f:
                    ftp.storbinary(f"STOR {item.remote}", f, BLOCK_SIZE, callback=block)
                on_done(index, item, Status.SENT, "")
                counts[Status.SENT] += 1
            except Cancelled:
                # The half-sent file would look complete by name: remove it.
                ftp = _reconnect_and_delete(conn, ftp, item.remote)
                on_done(index, item, Status.CANCELLED, "")
                counts[Status.CANCELLED] += 1
            except (OSError, ftplib.Error) as e:
                on_done(index, item, Status.FAILED, str(e))
                counts[Status.FAILED] += 1
                ftp = _reconnect_and_delete(conn, ftp, item.remote)
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()
    return counts


def _reconnect_and_delete(conn: Connection, ftp: ftplib.FTP, path: str) -> ftplib.FTP:
    """After an interrupted transfer the control connection may be unusable:
    open a fresh one and remove the partial file."""
    try:
        ftp.close()
    except ftplib.all_errors:
        pass
    fresh = connect(conn)
    try:
        fresh.delete(path)
    except ftplib.all_errors:
        pass
    return fresh
