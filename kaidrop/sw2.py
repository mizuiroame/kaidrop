"""SW2Transfer's HTTP API (port 6967), for sending and receiving faster than
FTP: a file is split in chunks moved over several connections at once
(about 50 MB/s up and 40 down, against about 9 over FTP). Browsing, folders
and the "already there?" questions stay on FTP; only the files' bytes come
this way, when the console runs SW2Transfer.

The API: GET /api/info, GET /api/list?path=, POST /api/create?path=&size=
then PUT /ul<path>?offset=N at each chunk, GET /dl<path> with Range,
POST /api/delete and /api/rename (which close SW2Transfer's cached handle
first), POST /api/login with the password. A request answered 410 was
cancelled on the console (Cancel all)."""
from __future__ import annotations

import ftplib
import http.client
import json
import posixpath
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

API_PORT = 6967
CONNECTIONS = 8              # SW2Transfer's own client: fastest with 8 connections
CHUNK = 2 * 1024 * 1024      # and 2 MB chunks.
PROBE_TIMEOUT_S = 1.5        # Looking for it on Connect: short, it's usually not there.
TIMEOUT_S = 30.0
TRIES = 3                    # A chunk whose connection broke is sent again on a new one.

BytesFn = Callable[[int], None]  # More bytes moved (called from several threads).


class Sw2Error(Exception):
    """SW2Transfer refused or failed; the message says why."""


class Sw2Cancelled(Sw2Error):
    """Stopped: by KaiDrop's Cancel, or Cancel all on the console."""


@dataclass(frozen=True)
class Sw2Info:
    version: str
    password: bool  # The console's SW2Transfer asks for one.


ABSENT_FOR_S = 30.0  # Not there: not asked again for this long (each batch asks).
_absent: dict[tuple[str, int], float] = {}


def probe(host: str, port: int = API_PORT, timeout: float = PROBE_TIMEOUT_S) -> Sw2Info | None:
    """SW2Transfer's answer at host, or None if it isn't there."""
    if time.monotonic() - _absent.get((host, port), -ABSENT_FOR_S) < ABSENT_FOR_S:
        return None
    info = _ask_info(host, port, timeout)
    if info is None:
        _absent[(host, port)] = time.monotonic()
    else:
        _absent.pop((host, port), None)
    return info


def _ask_info(host: str, port: int, timeout: float) -> Sw2Info | None:
    c = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        c.request("GET", "/api/info")
        r = c.getresponse()
        data = json.loads(r.read(64 * 1024) or b"{}")
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        c.close()
    if r.status != 200 or not isinstance(data, dict) or data.get("name") != "SW2Transfer":
        return None
    return Sw2Info(str(data.get("version", "")), bool(data.get("auth")))


def _quote(path: str) -> str:
    return urllib.parse.quote(path, safe="/")


class Sw2Client:
    """Several keep-alive connections to SW2Transfer (one per worker thread)."""

    def __init__(self, host: str, password: str = "", port: int = API_PORT, timeout: float = TIMEOUT_S,
                 connections: int = CONNECTIONS, chunk: int | None = None):
        self.host, self.port, self.timeout = host, port, timeout
        self.connections, self.chunk = connections, chunk or CHUNK
        self._password = password
        self._token: str | None = None
        self._auth_lock = threading.Lock()
        self._local = threading.local()
        self._opened: list[http.client.HTTPConnection] = []  # Every thread's, to close them all.
        self._pool = ThreadPoolExecutor(max_workers=connections, thread_name_prefix="sw2")

    # --- Requests ---

    def _conn(self) -> http.client.HTTPConnection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
            self._local.c = c
            with self._auth_lock:
                self._opened.append(c)
        return c

    def _drop(self) -> None:
        c = getattr(self._local, "c", None)
        if c is not None:
            c.close()
        self._local.c = None

    def login(self) -> None:
        """Signs in with the password (SW2Transfer's, which is also its FTP's)."""
        c = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            c.request("POST", "/api/login", headers={"X-SW2-Password": urllib.parse.quote(self._password, safe="")})
            r = c.getresponse()
            data = json.loads(r.read(64 * 1024) or b"{}")
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise Sw2Error(f"SW2Transfer's sign-in failed: {e}") from e
        finally:
            c.close()
        if r.status == 200 and data.get("ok"):
            self._token = data.get("token") or None
            return
        if r.status == 429:
            raise Sw2Error("SW2Transfer refuses sign-ins for a moment (too many wrong passwords).")
        raise Sw2Error("SW2Transfer's password is wrong (KaiDrop uses the FTP password for it).")

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        """Status, headers (lowercase names) and body. A broken connection is
        tried again on a new one; 401 signs in once; 410 is Sw2Cancelled."""
        signed_in = False
        last: Exception | None = None
        for _ in range(TRIES):
            sent_token = self._token
            h = {"User-Agent": "KaiDrop", **(headers or {})}
            if sent_token:
                h["Authorization"] = "Bearer " + sent_token
            try:
                c = self._conn()
                c.request(method, path, body=body, headers=h)
                r = c.getresponse()
                data = r.read()
            except (OSError, http.client.HTTPException) as e:
                last = e
                self._drop()
                continue
            got = {k.lower(): v for k, v in r.getheaders()}
            if got.get("connection", "").lower() == "close":
                self._drop()
            if r.status == 401 and not signed_in:
                signed_in = True
                with self._auth_lock:
                    if self._token == sent_token:  # Not signed in meanwhile by another connection.
                        self.login()
                continue
            if r.status == 410:
                self._drop()
                raise Sw2Cancelled("Cancelled on the console.")
            return r.status, got, data
        if isinstance(last, ConnectionRefusedError):
            raise Sw2Error("SW2Transfer stopped answering: was it closed on the console?")
        raise Sw2Error(f"SW2Transfer stopped answering: {last}")

    def api(self, method: str, endpoint: str, **params: object) -> dict:
        status, _, data = self.request(method, f"{endpoint}?{urllib.parse.urlencode(params)}")
        try:
            answer = json.loads(data or b"{}")
        except ValueError:
            answer = {}
        if status >= 300 or not isinstance(answer, dict) or answer.get("ok") is False:
            error = answer.get("error") if isinstance(answer, dict) else None
            raise Sw2Error(f"SW2Transfer: {error or f'HTTP {status}'}")
        return answer

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
        with self._auth_lock:
            opened, self._opened = self._opened, []
        for c in opened:
            c.close()

    # --- What's there ---

    def names(self, folder: str) -> set[str]:
        entries = self.api("GET", "/api/list", path=folder).get("entries", [])
        return {e["name"] for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)}

    def delete(self, path: str) -> None:
        self.api("POST", "/api/delete", path=path)

    def rename(self, source: str, target: str) -> None:
        """Never replaces what's at target (SW2Transfer's rule): delete it first."""
        self.api("POST", "/api/rename", **{"from": source, "to": target})

    # --- Moving bytes ---

    def _parallel(self, offsets: list[int], job: Callable[[int], None], cancel: threading.Event) -> None:
        """job(offset) for each, on the connections at once; the first error
        (or cancel) stops the rest and is raised."""
        def guarded(offset: int) -> None:
            if cancel.is_set():
                raise Sw2Cancelled("Cancelled.")
            job(offset)

        futures = [self._pool.submit(guarded, off) for off in offsets]
        done, pending = wait(futures, return_when=FIRST_EXCEPTION)
        failed = next((f.exception() for f in done if f.exception()), None)
        if failed:
            for f in pending:
                f.cancel()  # Those not started yet.
            wait(pending)
            raise failed
        if cancel.is_set():
            raise Sw2Cancelled("Cancelled.")

    def upload(self, local: Path, remote: str, on_bytes: BytesFn, cancel: threading.Event) -> None:
        """Writes the file local at remote, replacing it: in one request if
        it's small, else created at its size and sent in chunks at once."""
        size = local.stat().st_size
        xid = uuid.uuid4().hex  # Tags this file's requests, so Cancel all on the console stops them.
        url = f"/ul{_quote(remote)}"
        if size <= self.chunk:
            data = local.read_bytes()
            self._put(f"{url}?total={size}&x={xid}", data, remote)
            on_bytes(len(data))
            return
        self.api("POST", "/api/create", path=remote, size=size, x=xid)
        lock = threading.Lock()  # One handle for the whole file: Windows has no pread.

        with local.open("rb") as f:
            def put(offset: int) -> None:
                with lock:
                    f.seek(offset)
                    data = f.read(min(self.chunk, size - offset))
                self._put(f"{url}?offset={offset}&total={size}&x={xid}", data, remote)
                on_bytes(len(data))

            self._parallel(list(range(0, size, self.chunk)), put, cancel)

    def _put(self, path: str, data: bytes, remote: str) -> None:
        status, _, body = self.request("PUT", path, body=data, headers={
            "Content-Length": str(len(data)), "Content-Type": "application/octet-stream"})
        if status != 200:
            raise Sw2Error(f"SW2Transfer couldn't write {posixpath.basename(remote)}: "
                           f"HTTP {status} {body[:120].decode(errors='replace')}")

    def size_of(self, remote: str) -> int:
        status, headers, _ = self.request("HEAD", f"/dl{_quote(remote)}")
        if status != 200:
            raise Sw2Error(f"SW2Transfer can't read {posixpath.basename(remote)}: HTTP {status}")
        try:
            return int(headers.get("content-length", ""))
        except ValueError as e:
            raise Sw2Error("SW2Transfer didn't say the file's size.") from e

    def download(self, remote: str, local: Path, size: int, on_bytes: BytesFn, cancel: threading.Event) -> None:
        """Writes remote's size bytes into local (made anew), in chunks at once."""
        xid = uuid.uuid4().hex
        url = f"/dl{_quote(remote)}?x={xid}"
        # One handle for the whole file, open until it's whole: closing it after each
        # chunk let Windows (its virus check) look at the growing file again each time.
        lock = threading.Lock()
        with local.open("wb") as f:
            f.truncate(size)

            def get(offset: int) -> None:
                end = min(offset + self.chunk, size) - 1
                status, _, data = self.request("GET", url, headers={"Range": f"bytes={offset}-{end}"})
                if status not in (200, 206) or len(data) != end - offset + 1:
                    raise Sw2Error(f"SW2Transfer sent {len(data)} bytes of {posixpath.basename(remote)} "
                                   f"at {offset} (HTTP {status}).")
                with lock:
                    f.seek(offset)
                    f.write(data)
                on_bytes(len(data))

            if size:
                self._parallel(list(range(0, size, self.chunk)), get, cancel)


def for_ftp(host: str, password: str, ftp: ftplib.FTP, on_note: Callable[[str], None],
            port: int = API_PORT) -> Sw2Client | None:
    """open_for, with the FTP connection's root to compare; what it found goes to on_note."""
    if probe(host, port) is None:
        return None  # Not there: FTP isn't touched.
    try:
        root = {name for name, _ in ftp.mlsd("/") if name not in (".", "..")}
        ftp.voidcmd("TYPE I")  # Listing left it in ASCII, where servers refuse SIZE.
    except ftplib.all_errors:
        return None  # No MLSD: nothing to compare with, so FTP alone.
    client, note = open_for(host, password, root, port)
    if note:
        on_note(note)
    return client


def open_for(host: str, password: str, root_names: set[str], port: int = API_PORT) -> tuple[Sw2Client | None, str]:
    """A client for the console at host if SW2Transfer runs there and sees
    the same card as the FTP server (root_names: the FTP root's names), with
    a line for the log either way."""
    info = probe(host, port)
    if info is None:
        return None, ""
    client = Sw2Client(host, password, port)
    try:
        if info.password:
            client.login()
        if client.names("/") != root_names:
            client.close()
            return None, "SW2Transfer is on the console, but it doesn't show the same folders as FTP: using FTP."
    except Sw2Error as e:
        client.close()
        return None, f"{e} Using FTP."
    return client, f"SW2Transfer {info.version} found: files move over {client.connections} connections at once."
