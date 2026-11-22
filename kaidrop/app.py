"""KaiDrop's window: this computer on the left, the server on the right, and
the transfer queue below. Drag files or folders from one side to the other
(or right-click) to send them to the server or receive them from it."""
from __future__ import annotations

import posixpath
from datetime import datetime
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from . import __version__, settings
from .appicon import APP_ICONS
from .batch import Batch, leftover
from .conflict import ConflictDialog, Side
from .download import DownloadItem, DownloadPlan, LocalFile, download, plan_download
from .dragdrop import Drag, Target
from .ftp import Choice, Connection, RemoteFile, Status, upload
from .logview import ERROR, GOOD, INFO, LogView
from .panes import LocalPane, RemotePane, human_size
from .plan import UploadItem, build_plan
from .rate import RateMeter, describe
from .remote import CONNECTED, CONNECTING, LOST, RemoteSession, _reason

try:  # Drops from Explorer or Finder, when tkinterdnd2 is installed.
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    _Root = tk.Tk

POLL_MS = 60
RATE_EVERY_S = 0.25  # How often the speed and time left are redrawn.
EXPLANATION = ("Switch 2 hides files and folders whose names have accents (á, ñ…) or other non-ASCII "
               "characters: they are saved, but no app on the console can see them. With plain names on, the "
               "copies on the console get names it can list. Your files here are never renamed.")


class KaiDrop(_Root):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"KaiDrop {__version__}")
        self._icons = [tk.PhotoImage(data=data) for data in APP_ICONS]  # Kept: Tk drops unreferenced images.
        self.iconphoto(True, *self._icons)
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.saved = settings.load()
        self.events: queue.Queue = queue.Queue()  # Callables to run on this thread.
        self.jobs: queue.Queue = queue.Queue()    # Batches to send, in order.
        self.cancel = threading.Event()
        self.session: RemoteSession | None = None
        self.conn: Connection | None = None
        self.link_state = ""  # The session's connection state; "" when not connected.
        self.sending = False
        self.queue_rows = 0
        self.receiving_rows: set[str] = set()  # Rows of downloads, to word their status.
        self.ended: dict[str, Status] = {}     # How each row's transfer ended.
        self.stopped: list[Batch] = []         # What was left when the connection went, to continue.
        self.meter = RateMeter()
        self.rate_drawn = 0.0                  # When the speed was last redrawn.
        self._build()
        threading.Thread(target=self._transfer_worker, daemon=True).start()
        self.after(POLL_MS, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # --- Layout ---

    def _build(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        conn = ttk.Frame(self)
        conn.pack(fill="x", padx=10, pady=(10, 4))
        self.host = tk.StringVar(value=self.saved.host)
        self.port = tk.StringVar(value=self.saved.port)
        self.user = tk.StringVar(value=self.saved.user)
        self.password = tk.StringVar()
        for label, var, width, show in [("Host", self.host, 16, ""), ("Port", self.port, 6, ""),
                                        ("User", self.user, 12, ""), ("Password", self.password, 12, "•")]:
            ttk.Label(conn, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(conn, textvariable=var, width=width, show=show).pack(side="left", padx=(0, 12))
        self.connect_button = ttk.Button(conn, text="Connect", command=self._toggle_connection)
        self.connect_button.pack(side="left")
        self.link = ttk.Label(conn, text="● Not connected", foreground="#888")
        self.link.pack(side="left", padx=(10, 0))
        self.plain = tk.BooleanVar(value=self.saved.plain_names)
        ttk.Checkbutton(conn, text="Plain names for Switch 2", variable=self.plain).pack(side="right")
        ttk.Label(self, text=EXPLANATION, wraplength=1140, foreground="#666").pack(fill="x", padx=12)

        panes = ttk.PanedWindow(self, orient="horizontal")
        self.local = LocalPane(panes, self.saved.local_folder, self._send_selected)
        # The server opens at its root.
        self.remote = RemotePane(panes, "/", self._set_status, self.plain.get, self._download_selected)
        panes.add(self.local, weight=1)
        panes.add(self.remote, weight=1)

        connected = lambda: self.session is not None  # noqa: E731
        remote_folder = lambda row: posixpath.join(self.remote.path, row) if row else self.remote.path  # noqa: E731
        Drag(self, self.local, [Target(self.remote, "Send", remote_folder,
                                       lambda row: self._queue_send(self.local.selected_paths(),
                                                                    self._remote_folder(row)), connected)])
        Drag(self, self.remote, [
            Target(self.local, "Receive", lambda row: str(self.local.path / row) if row else str(self.local.path),
                   lambda row: self._download(self.remote.selected(), self._local_folder(row)), connected),
            # Onto one of the server's own folders: moved there.
            Target(self.remote, "Move", remote_folder,
                   lambda row: self.remote.move_into(
                       [(posixpath.join(self.remote.path, name), is_dir) for name, is_dir in self.remote.selected()],
                       self._remote_folder(row)),
                   connected, folders_only=True)])
        if DND_FILES:
            self.remote.tree.drop_target_register(DND_FILES)
            self.remote.tree.dnd_bind("<<Drop>>", self._os_drop)

        lower = ttk.Frame(self)
        lower.pack(side="bottom", fill="x", padx=10)
        head = ttk.Frame(lower)
        head.pack(fill="x")
        self.cancel_button = ttk.Button(head, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right")
        ttk.Button(head, text="Clear finished", command=self._clear_finished).pack(side="right", padx=6)
        self.rate = ttk.Label(head, foreground="#555")
        self.rate.pack(side="left")
        tabs = ttk.Notebook(lower)
        tabs.pack(fill="x", pady=(0, 4))
        self.queue = ttk.Treeview(tabs, columns=("remote", "size", "status"), height=7)
        for col, title, width in [("#0", "From", 380), ("remote", "To", 420),
                                  ("size", "Size", 90), ("status", "Status", 140)]:
            self.queue.heading(col, text=title)
            self.queue.column(col, width=width, anchor="e" if col == "size" else "w")
        self.queue.tag_configure("renamed", foreground="#a0408c")
        self.queue.tag_configure("failed", foreground="#c0392b")
        self.log = LogView(tabs)
        tabs.add(self.queue, text="Transfers")
        tabs.add(self.log, text="Log")
        self.progress = ttk.Progressbar(lower, mode="determinate")
        self.progress.pack(fill="x")
        self.status = ttk.Label(self, text="Type the console's address (OunceShell's FTP screen shows it) and Connect.")
        self.status.pack(side="bottom", fill="x", padx=12, pady=(4, 10), before=lower)
        # Packed last, the panes get the height left: the transfers and status line always show.
        panes.pack(fill="both", expand=True, padx=10, pady=8)

    def _set_status(self, text: str, kind: str = INFO) -> None:
        """The status line, and the log."""
        self.status.config(text=text)
        self.log.add(text, kind)

    # --- Connecting ---

    def _connection(self) -> Connection | None:
        host = self.host.get().strip()
        if not host:
            messagebox.showwarning("KaiDrop", "Type the server's address, as OunceShell's FTP screen shows it.")
            return None
        if not self.port.get().strip().isdigit():
            messagebox.showwarning("KaiDrop", "The port is a number, as OunceShell's FTP screen shows it.")
            return None
        return Connection(host, int(self.port.get()), self.user.get().strip() or "anonymous", self.password.get())

    def _toggle_connection(self) -> None:
        """Connect, Disconnect, or Reconnect after the connection was lost."""
        if self.session and self.link_state != LOST:
            self.session.close()
            self.session = None
            self.remote.attach(None)
            self._show_link("", "Disconnected.")
            return
        if self.session:
            self.session.close()
            self.session = None
        conn = self._connection()
        if not conn:
            return
        self.conn = conn
        session = RemoteSession(conn, self.events.put, lambda state, msg: self._link_changed(session, state, msg))
        self.session = session
        self.connect_button.config(text="Disconnect")
        self.remote.attach(session)
        self._remember()

    def _link_changed(self, session: RemoteSession, state: str, message: str) -> None:
        if session is self.session:  # Not one closed since.
            self._show_link(state, message)

    def _show_link(self, state: str, message: str) -> None:
        self.link_state = state
        text, color = {CONNECTING: ("● Connecting…", "#b7791f"), CONNECTED: ("● Connected", "#1e7d32"),
                       LOST: ("● Connection lost", "#c0392b")}.get(state, ("● Not connected", "#888"))
        self.link.config(text=text, foreground=color)
        self.connect_button.config(text={LOST: "Reconnect", "": "Connect"}.get(state, "Disconnect"))
        if state == CONNECTED:
            self.log.add(message, GOOD)  # The server's welcome: the log only.
            if self.stopped:
                self._offer_to_continue()
        elif state == LOST:
            self._set_status(message.rstrip(". ") + ". Press Reconnect to try again.", ERROR)
        else:
            self._set_status(message)

    def _remember(self) -> None:
        settings.save(settings.Settings(self.host.get().strip(), self.port.get().strip(), self.user.get().strip(),
                                        self.remote.path, self.plain.get(), str(self.local.path)))

    # --- Choosing what to send ---

    def _send_selected(self) -> None:
        paths = self.local.selected_paths()
        if not paths:
            self._set_status("Select files or folders on the left, then drag them to the right (or right-click).")
            return
        self._queue_send(paths, self.remote.path)

    def _remote_folder(self, row: str | None) -> str:
        """Dropped on a folder row: into it; anywhere else: the folder shown."""
        return posixpath.join(self.remote.path, row) if row else self.remote.path

    def _local_folder(self, row: str | None) -> Path:
        return self.local.path / row if row else self.local.path

    def _os_drop(self, event) -> None:
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        row = self.remote.row_at(event.y_root - self.remote.tree.winfo_rooty())
        self._queue_send(paths, self._remote_folder(row[0] if row and row[1] else None))

    # --- Choosing what to receive ---

    def _download_selected(self) -> None:
        self._download(self.remote.selected(), self.local.path)

    def _download(self, rows: list[tuple[str, bool]], folder: Path) -> None:
        """Lists the chosen server files and folders (on the browsing
        connection), then queues them to come into folder."""
        if not self.session or not self.conn:
            messagebox.showinfo("KaiDrop", "Connect to the server first.")
            return
        if not rows:
            self._set_status("Select files or folders on the right, then drag them to the left (or right-click).")
            return
        sources = [(posixpath.join(self.remote.path, name), is_dir) for name, is_dir in rows]
        self._set_status(f"Listing what to receive from {self.remote.path}…")
        self.session.submit(lambda ftp: plan_download(ftp, sources, folder),
                            lambda plan, f=folder: self._queue_download(plan, f),
                            lambda m: self._set_status(f"Can't list what to receive: {m}", ERROR))

    def _queue_download(self, plan: DownloadPlan, folder: Path) -> None:
        if not plan.items or not self.conn:
            self._set_status("Nothing to receive there (empty folders?).")
            return
        rows = []
        for item in plan.items:
            iid = self._new_row()
            rows.append(iid)
            self.receiving_rows.add(iid)
            self.queue.insert("", "end", iid=iid, text=item.remote,
                              values=(str(item.local), human_size(item.size), "Waiting"))
        self._start(Batch("down", plan, tuple(rows), folder))
        self._set_status(f"Queued {len(plan.items)} files to receive ({human_size(plan.total_bytes)}).")

    # --- Transfers (a worker thread sends one batch after another) ---

    def _queue_send(self, sources: list[Path], folder: str) -> None:
        if not self.session or not self.conn:
            messagebox.showinfo("KaiDrop", "Connect to the server first.")
            return
        plan = build_plan(sources, folder, self.plain.get())
        if not plan.items:
            self._set_status("Nothing to send there (empty folders?).")
            return
        rows = []
        for item in plan.items:
            iid = self._new_row()
            rows.append(iid)
            text = str(Path(*item.local.parts[-2:]))
            if item.playlist_changes:  # Its copy will point to the songs' names on the console.
                count = item.playlist_changes
                text += f"  (playlist: {count} {'entry' if count == 1 else 'entries'} renamed)"
            self.queue.insert("", "end", iid=iid, text=text,
                              values=(item.remote, human_size(item.size), "Waiting"),
                              tags=("renamed",) if item.renamed or item.playlist_changes else ())
        self._start(Batch("up", plan, tuple(rows), folder))
        self._remember()
        renamed = f", {plan.renamed_count} with plain names" if plan.renamed_count else ""
        self._set_status(f"Queued {len(plan.items)} files ({human_size(plan.total_bytes)}){renamed}.")

    def _new_row(self) -> str:
        iid = str(self.queue_rows)
        self.queue_rows += 1
        return iid

    def _start(self, batch: Batch) -> None:
        self.sending = True
        self.jobs.put((batch, self.conn))

    def _transfer_worker(self) -> None:
        while True:
            batch, conn = self.jobs.get()
            post: Callable = self.events.put
            receiving, plan, rows, folder = batch.kind == "down", batch.plan, batch.rows, batch.folder
            post(lambda p=plan, r=receiving: self._started(p, r))
            progress = lambda i, item, sent, total: post(lambda r=rows[i], t=total: self._progress(r, t))  # noqa: E731
            done = lambda i, item, st, msg: post(  # noqa: E731
                lambda r=rows[i], s=st, m=msg, n=item.size: self._row_done(r, s, m, n))
            try:
                if receiving:
                    counts = download(conn, plan, progress, done, self.cancel, self._ask_download_from_worker)
                else:
                    counts = upload(conn, plan, progress, done, self.cancel, self._ask_from_worker)
                post(lambda c=counts, d=folder, r=receiving: self._finished(c, d, r))
            except Exception as e:  # Connection problems end this batch with a message.
                post(lambda b=batch, m=_reason(e): self._failed(b, m))

    def _ask(self, where: str, folder: str, existing: Side, incoming: Side) -> tuple[Choice, bool]:
        """Asks on the window's thread what to do with a file already there;
        the transfer thread waits for the answer."""
        answer: queue.Queue = queue.Queue(maxsize=1)
        self.events.put(lambda: answer.put(ConflictDialog(self, where, folder, existing, incoming).ask()))
        return answer.get()

    def _ask_from_worker(self, item: UploadItem, remote: RemoteFile) -> tuple[Choice, bool]:
        mtime = datetime.fromtimestamp(item.local.stat().st_mtime) if item.local.exists() else None
        return self._ask("on the server", posixpath.dirname(remote.path) or "/",
                         Side("On the server", posixpath.basename(remote.path), remote.size, remote.modified),
                         Side("Being sent", item.local.name, item.size, mtime))

    def _ask_download_from_worker(self, item: DownloadItem, here: LocalFile,
                                  server_time: datetime | None) -> tuple[Choice, bool]:
        return self._ask("on this computer", str(here.path.parent),
                         Side("On this computer", here.path.name, here.size, here.modified),
                         Side("Being received", posixpath.basename(item.remote), item.size, server_time))

    def _started(self, plan, receiving: bool) -> None:
        verb = "Receiving" if receiving else "Sending"
        self.log.add(f"{verb} {len(plan.items)} files ({human_size(plan.total_bytes)})…")
        self.sending = True
        self.cancel.clear()
        self.cancel_button.config(state="normal")
        self.progress.config(maximum=max(plan.total_bytes, 1), value=0)
        self.meter.start(plan.total_bytes)
        self.rate.config(text=describe(0, plan.total_bytes, None, None))

    def _progress(self, iid: str, total: int) -> None:
        self.progress.config(value=total)
        self.meter.update(total)
        now = self.meter.clock()
        if now - self.rate_drawn >= RATE_EVERY_S:
            self.rate_drawn = now
            self.rate.config(text=describe(total, self.meter.total, self.meter.speed(), self.meter.remaining()))
        if self.queue.exists(iid) and self.queue.set(iid, "status") == "Waiting":
            self.queue.set(iid, "status", "Receiving…" if iid in self.receiving_rows else "Sending…")

    def _row_done(self, iid: str, status: Status, message: str, size: int = 0) -> None:
        self.ended[iid] = status
        if status is Status.SKIPPED:
            self.meter.skip(size)
        if not self.queue.exists(iid):
            return
        text = status.value
        if iid in self.receiving_rows:
            text = {Status.SENT: "Received", Status.COPY: "Saved as a copy"}.get(status, text)
        self.queue.set(iid, "status", text if status is not Status.FAILED else f"Failed: {message}"[:40])
        if status is Status.COPY:
            self.queue.set(iid, "remote", message)
        elif status is Status.SENT and message:
            self.log.add(message)  # What a playlist's copy points to.
        if status is Status.FAILED:
            self.queue.item(iid, tags=(*self.queue.item(iid, "tags"), "failed"))
            self.log.add(f"Failed: {self.queue.set(iid, 'remote')}: {message}", ERROR)
        self.queue.see(iid)

    def _finished(self, counts: dict, folder, receiving: bool = False) -> None:
        self._end_batch()
        verb = "received" if receiving else "sent"
        copies = f", {counts[Status.COPY]} {verb} as copies" if counts[Status.COPY] else ""
        self._set_status(f"Done: {counts[Status.SENT]} {verb}{copies}, {counts[Status.SKIPPED]} skipped, "
                         f"{counts[Status.FAILED]} failed, {counts[Status.CANCELLED]} cancelled.",
                         ERROR if counts[Status.FAILED] else GOOD)
        if receiving:
            self.local.refresh()  # Show what arrived.
        elif self.session and str(folder).startswith(self.remote.path):
            self.remote.refresh(quiet=True)

    def _failed(self, batch: Batch, message: str) -> None:
        """The connection went mid-batch: what's left waits for Reconnect."""
        self._end_batch()
        rest = leftover(batch, self.ended)
        if not rest:
            self._set_status(f"Stopped: {message}", ERROR)
            return
        first_stop = not self.stopped
        self.stopped.append(rest)
        for iid in rest.rows:
            if self.queue.exists(iid):
                self.queue.set(iid, "status", "Stopped")
        left = sum(len(b.rows) for b in self.stopped)
        if self.session and self.link_state != LOST:
            # Browsing uses its own connection, which would only notice at its next keepalive:
            # show the connection lost now, with Reconnect.
            self.session.mark_lost(f"The transfer stopped: {message}; {left} files left")
        else:
            self._set_status(f"Stopped: {message}. {left} files left: they can continue after Reconnect.", ERROR)
        if first_stop:  # Batches queued behind it stop too: one message is enough.
            messagebox.showerror("KaiDrop", f"The transfer stopped: {message}\n\n"
                                 "Start the server again and press Reconnect to continue with the files left.")

    def _offer_to_continue(self) -> None:
        batches, self.stopped = self.stopped, []
        left = sum(len(b.rows) for b in batches)
        if not messagebox.askyesno("KaiDrop", f"{left} files were left when the connection was lost. "
                                   "Continue with them now?"):
            self._set_status(f"{left} files left as they were.")
            return
        for batch in batches:
            for iid in batch.rows:
                if self.queue.exists(iid):
                    self.queue.set(iid, "status", "Waiting")
                    self.queue.item(iid, tags=tuple(t for t in self.queue.item(iid, "tags") if t != "failed"))
            self._start(batch)
        self._set_status(f"Continuing with {left} files.")

    def _end_batch(self) -> None:
        self.rate.config(text="")
        self.sending = not self.jobs.empty()
        self.cancel_button.config(state="normal" if self.sending else "disabled")

    def _cancel(self) -> None:
        self.cancel.set()  # Stops the batch being sent; batches queued after it still go.
        self._set_status("Cancelling…")

    def _clear_finished(self) -> None:
        for iid in self.queue.get_children():
            if self.queue.set(iid, "status") not in ("Waiting", "Sending…", "Receiving…", "Stopped"):
                self.queue.delete(iid)
                self.receiving_rows.discard(iid)
                self.ended.pop(iid, None)

    def _poll(self) -> None:
        try:
            while True:
                self.events.get_nowait()()
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _close(self) -> None:
        if self.sending and not messagebox.askyesno("KaiDrop", "A transfer is running. Stop it and quit?"):
            return
        self.cancel.set()
        self._remember()
        if self.session:
            self.session.close()
        self.destroy()


def main() -> None:
    KaiDrop().mainloop()
