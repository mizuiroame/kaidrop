"""Browsing the server: folder listings, and a connection on its own thread
so the window never waits on the network."""
from __future__ import annotations

import ftplib
import posixpath
import queue
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

from .ftp import Connection, connect


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    is_dir: bool
    size: int  # 0 for folders, or when the server doesn't say.


# "drwxr-xr-x 1 owner group 4096 Jan 01 12:00 name" (the usual UNIX style).
_UNIX = re.compile(r"^([dl-])[rwxsStT-]{9}\S*\s+\d+\s+\S+\s+\S+\s+(\d+)\s+\w{3}\s+\d+\s+[\d:]+\s+(.+)$")
# "01-31-24  10:00AM       <DIR>          name" (the Windows style).
_DOS = re.compile(r"^\d{2}-\d{2}-\d{2,4}\s+\d{1,2}:\d{2}[AP]M\s+(<DIR>|\d+)\s+(.+)$", re.IGNORECASE)


def parse_list_line(line: str) -> RemoteEntry | None:
    """One line of a LIST reply, or None if it isn't an entry."""
    m = _UNIX.match(line)
    if m:
        name = m.group(3)
        if m.group(1) == "l" and " -> " in name:
            name = name.split(" -> ", 1)[0]  # A link: list it by its own name.
        return None if name in (".", "..") else RemoteEntry(name, m.group(1) == "d", int(m.group(2)))
    m = _DOS.match(line)
    if m:
        is_dir = m.group(1).upper() == "<DIR>"
        return RemoteEntry(m.group(2), is_dir, 0 if is_dir else int(m.group(1)))
    return None


def sort_entries(entries: list[RemoteEntry]) -> list[RemoteEntry]:
    """Folders first, then files, by name ignoring case."""
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def list_dir(ftp: ftplib.FTP, path: str) -> list[RemoteEntry]:
    """The folder's entries, with MLSD when the server has it, else LIST."""
    try:
        entries = [RemoteEntry(name, facts.get("type") == "dir", int(facts.get("size", 0) or 0))
                   for name, facts in ftp.mlsd(path, facts=["type", "size"])
                   if facts.get("type") in ("dir", "file")]
        return sort_entries(entries)
    except (ftplib.error_perm, ftplib.error_reply):
        pass
    lines: list[str] = []
    ftp.retrlines(f"LIST {path}", lines.append)
    return sort_entries([e for e in (parse_list_line(line) for line in lines) if e])


def parent(path: str) -> str:
    return posixpath.dirname(path.rstrip("/")) or "/"


def delete_tree(ftp: ftplib.FTP, path: str, is_dir: bool) -> None:
    """Deletes a file, or a folder with everything in it."""
    if not is_dir:
        ftp.delete(path)
        return
    for entry in list_dir(ftp, path):
        delete_tree(ftp, posixpath.join(path, entry.name), entry.is_dir)
    ftp.rmd(path)


# Connection states reported by a session.
CONNECTING, CONNECTED, LOST = "connecting", "connected", "lost"
KEEPALIVE_S = 20  # Idle this long, the session checks that the server is still there.

StateFn = Callable[[str, str], None]  # state, message


@dataclass(frozen=True)
class _Lost:
    message: str


class RemoteSession:
    """One connection, used by one worker thread. Jobs run in order; their
    results come back through `post`, which must hand them to the window's
    thread (for example with a queue the window polls).

    on_state hears when the session connects, and when the connection is
    lost: a failed connect, or a server that stopped answering while idle.
    The next job connects again."""

    def __init__(self, conn: Connection, post: Callable[[Callable[[], None]], None],
                 on_state: StateFn | None = None) -> None:
        self.conn = conn
        self._post = post
        self._on_state = on_state
        self._jobs: queue.Queue = queue.Queue()
        self._ftp: ftplib.FTP | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, job: Callable[[ftplib.FTP], Any], on_result: Callable[[Any], None],
               on_error: Callable[[str], None]) -> None:
        self._jobs.put((job, on_result, on_error))

    def post(self, fn: Callable[[], None]) -> None:
        """Hands fn to the window's thread: for a job to say how it's going."""
        self._post(fn)

    def close(self) -> None:
        self._jobs.put(None)

    def mark_lost(self, message: str) -> None:
        """Another connection to the same server (a transfer's) found it gone:
        drop this one too and report it lost, without waiting for the
        keepalive. The next job connects again."""
        self._jobs.put(_Lost(message))

    def _state(self, state: str, message: str) -> None:
        if self._on_state:
            self._post(lambda f=self._on_state: f(state, message))

    def _connection(self) -> ftplib.FTP:
        if self._ftp is None:
            self._state(CONNECTING, f"Connecting to {self.conn.host}:{self.conn.port}…")
            try:
                self._ftp = connect(self.conn)
            except Exception as e:
                self._state(LOST, f"Can't connect to {self.conn.host}:{self.conn.port}: {_reason(e)}")
                raise
            self._state(CONNECTED, self._ftp.getwelcome() or "Connected.")
        return self._ftp

    def _run(self) -> None:
        while True:
            try:
                item = self._jobs.get(timeout=KEEPALIVE_S)
            except queue.Empty:
                self._keepalive()
                continue
            if item is None:
                break
            if isinstance(item, _Lost):
                self._drop()
                self._state(LOST, item.message)
                continue
            job, on_result, on_error = item
            try:
                result = self._attempt(job)
                self._post(lambda r=result, f=on_result: f(r))
            except Exception as e:  # Shown to the user by on_error.
                self._post(lambda m=_reason(e), f=on_error: f(m))
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except ftplib.all_errors:
                self._ftp.close()

    def _keepalive(self) -> None:
        if self._ftp is None:
            return  # Not connected, or already reported lost.
        try:
            self._ftp.voidcmd("NOOP")
        except Exception as e:  # Closed, reset, timed out, or a 421 goodbye.
            self._drop()
            self._state(LOST, f"The server stopped answering: {_reason(e)}")

    def _drop(self) -> None:
        if self._ftp is not None:
            try:
                self._ftp.close()
            except ftplib.all_errors:
                pass
        self._ftp = None

    def _attempt(self, job: Callable[[ftplib.FTP], Any]) -> Any:
        was_open = self._ftp is not None
        try:
            return job(self._connection())
        except (OSError, EOFError, ftplib.error_temp):
            if not was_open:
                raise  # A new connection failed: trying again won't help.
            # The connection dropped (the console slept, the server restarted): once more on a new one.
            self._drop()
            return job(self._connection())


def _reason(e: BaseException) -> str:
    """Why the connection failed, in words (not Windows' "WinError 10061…")."""
    if isinstance(e, ConnectionRefusedError):
        return "the server isn't running (is the FTP server on?)"
    if isinstance(e, TimeoutError):
        return "the server didn't answer (is the console awake and on the same network?)"
    if isinstance(e, (ConnectionResetError, ConnectionAbortedError)):
        return "the connection was cut"
    text = str(e).strip()
    if isinstance(e, EOFError) or not text:
        return "the server closed the connection" if isinstance(e, EOFError) else type(e).__name__
    return text
