"""KaiDrop's window: this computer on the left, the server on the right, and
the transfer queue below. Drag files or folders onto the server to send them."""
from __future__ import annotations

import posixpath
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from . import __version__, settings
from .ftp import Connection, Status, upload
from .panes import LocalPane, RemotePane, human_size
from .plan import build_plan
from .remote import RemoteSession

try:  # Drops from Explorer or Finder, when tkinterdnd2 is installed.
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    _Root = tk.Tk

POLL_MS = 60
DRAG_THRESHOLD = 8
EXPLANATION = ("Switch 2 hides files and folders whose names have accents (á, ñ…) or other non-ASCII "
               "characters: they are saved, but no app on the console can see them. With plain names on, the "
               "copies on the console get names it can list. Your files here are never renamed.")


class KaiDrop(_Root):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"KaiDrop {__version__}")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.saved = settings.load()
        self.events: queue.Queue = queue.Queue()  # Callables to run on this thread.
        self.jobs: queue.Queue = queue.Queue()    # Batches to send, in order.
        self.cancel = threading.Event()
        self.session: RemoteSession | None = None
        self.conn: Connection | None = None
        self.sending = False
        self.queue_rows = 0
        self._drag_start: tuple[int, int] | None = None
        self._dragging = False
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
        self.plain = tk.BooleanVar(value=self.saved.plain_names)
        ttk.Checkbutton(conn, text="Plain names for Switch 2", variable=self.plain).pack(side="right")
        ttk.Label(self, text=EXPLANATION, wraplength=1140, foreground="#666").pack(fill="x", padx=12)

        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=8)
        self.local = LocalPane(panes, self.saved.local_folder, self._send_selected)
        middle = ttk.Frame(panes, width=70)
        ttk.Button(middle, text="Send →", command=self._send_selected).pack(expand=True, padx=6)
        # The server opens at its root.
        self.remote = RemotePane(panes, "/", self._set_status, self.plain.get)
        panes.add(self.local, weight=1)
        panes.add(middle, weight=0)
        panes.add(self.remote, weight=1)

        tree = self.local.tree  # Dragging from the left list onto the server.
        tree.bind("<ButtonPress-1>", self._drag_press, add="+")
        tree.bind("<B1-Motion>", self._drag_motion, add="+")
        tree.bind("<ButtonRelease-1>", self._drag_release, add="+")
        if DND_FILES:
            self.remote.tree.drop_target_register(DND_FILES)
            self.remote.tree.dnd_bind("<<Drop>>", self._os_drop)

        lower = ttk.Frame(self)
        lower.pack(fill="x", padx=10)
        head = ttk.Frame(lower)
        head.pack(fill="x")
        ttk.Label(head, text="Transfers", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.cancel_button = ttk.Button(head, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right")
        ttk.Button(head, text="Clear finished", command=self._clear_finished).pack(side="right", padx=6)
        self.queue = ttk.Treeview(lower, columns=("remote", "size", "status"), height=7)
        for col, title, width in [("#0", "From this computer", 380), ("remote", "To the server", 420),
                                  ("size", "Size", 90), ("status", "Status", 140)]:
            self.queue.heading(col, text=title)
            self.queue.column(col, width=width, anchor="e" if col == "size" else "w")
        self.queue.tag_configure("renamed", foreground="#a0408c")
        self.queue.tag_configure("failed", foreground="#c0392b")
        self.queue.pack(fill="x", pady=4)
        self.progress = ttk.Progressbar(lower, mode="determinate")
        self.progress.pack(fill="x")
        self.status = ttk.Label(self, text="Type the console's address (OunceShell's FTP screen shows it) and Connect.")
        self.status.pack(fill="x", padx=12, pady=(4, 10))

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

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
        if self.session:
            self.session.close()
            self.session = None
            self.remote.attach(None)
            self.connect_button.config(text="Connect")
            self._set_status("Disconnected.")
            return
        conn = self._connection()
        if not conn:
            return
        self.conn = conn
        self.session = RemoteSession(conn, self.events.put)
        self.connect_button.config(text="Disconnect")
        self.remote.attach(self.session)
        self._remember()

    def _remember(self) -> None:
        settings.save(settings.Settings(self.host.get().strip(), self.port.get().strip(), self.user.get().strip(),
                                        self.remote.path, self.plain.get(), str(self.local.path)))

    # --- Choosing what to send ---

    def _send_selected(self) -> None:
        paths = self.local.selected_paths()
        if not paths:
            self._set_status("Select files or folders on the left, then Send → (or drag them to the right).")
            return
        self._queue_send(paths, self.remote.path)

    def _drag_press(self, event: tk.Event) -> None:
        self._drag_start = (event.x_root, event.y_root)
        self._dragging = False

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_start and not self._dragging:
            dx, dy = event.x_root - self._drag_start[0], event.y_root - self._drag_start[1]
            if abs(dx) + abs(dy) > DRAG_THRESHOLD and self.local.selected():
                self._dragging = True
                self.config(cursor="hand2")

    def _drag_release(self, event: tk.Event) -> None:
        dragging, self._dragging, self._drag_start = self._dragging, False, None
        self.config(cursor="")
        if not dragging:
            return
        if self.winfo_containing(event.x_root, event.y_root) is not self.remote.tree:
            return
        self._queue_send(self.local.selected_paths(), self._drop_folder(event.y_root))

    def _drop_folder(self, y_root: int) -> str:
        """Dropped on a folder row: into it; anywhere else: the folder shown."""
        row = self.remote.row_at(y_root - self.remote.tree.winfo_rooty())
        if row and row[1]:
            return posixpath.join(self.remote.path, row[0])
        return self.remote.path

    def _os_drop(self, event) -> None:
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        self._queue_send(paths, self._drop_folder(event.y_root))

    # --- Transfers (a worker thread sends one batch after another) ---

    def _queue_send(self, sources: list[Path], folder: str) -> None:
        if not self.session or not self.conn:
            messagebox.showinfo("KaiDrop", "Connect to the server first.")
            return
        plan = build_plan(sources, folder, self.plain.get())
        if not plan.items:
            self._set_status("Nothing to send there (empty folders?).")
            return
        first = self.queue_rows
        for item in plan.items:
            iid = str(self.queue_rows)
            self.queue_rows += 1
            self.queue.insert("", "end", iid=iid, text=str(Path(*item.local.parts[-2:])),
                              values=(item.remote, human_size(item.size), "Waiting"),
                              tags=("renamed",) if item.renamed else ())
        self.sending = True
        self.jobs.put((self.conn, plan, first, folder))
        self._remember()
        renamed = f", {plan.renamed_count} with plain names" if plan.renamed_count else ""
        self._set_status(f"Queued {len(plan.items)} files ({human_size(plan.total_bytes)}){renamed}.")

    def _transfer_worker(self) -> None:
        while True:
            conn, plan, first, folder = self.jobs.get()
            post: Callable = self.events.put
            post(lambda p=plan: self._started(p))
            try:
                counts = upload(conn, plan,
                                lambda i, item, sent, total: post(lambda r=first + i, t=total: self._progress(r, t)),
                                lambda i, item, st, msg: post(lambda r=first + i, s=st, m=msg: self._row_done(r, s, m)),
                                self.cancel)
                post(lambda c=counts, d=folder: self._finished(c, d))
            except Exception as e:  # Connection problems end this batch with a message.
                post(lambda m=str(e): self._failed(m))

    def _started(self, plan) -> None:
        self.sending = True
        self.cancel.clear()
        self.cancel_button.config(state="normal")
        self.progress.config(maximum=max(plan.total_bytes, 1), value=0)

    def _progress(self, row: int, total: int) -> None:
        self.progress.config(value=total)
        if self.queue.exists(str(row)) and self.queue.set(str(row), "status") == "Waiting":
            self.queue.set(str(row), "status", "Sending…")

    def _row_done(self, row: int, status: Status, message: str) -> None:
        iid = str(row)
        if not self.queue.exists(iid):
            return
        self.queue.set(iid, "status", status.value if status is not Status.FAILED else f"Failed: {message}"[:40])
        if status is Status.FAILED:
            self.queue.item(iid, tags=("failed",))
        self.queue.see(iid)

    def _finished(self, counts: dict, folder: str) -> None:
        self._end_batch()
        self._set_status(f"Done: {counts[Status.SENT]} sent, {counts[Status.SKIPPED]} already there, "
                         f"{counts[Status.FAILED]} failed, {counts[Status.CANCELLED]} cancelled.")
        if self.session and folder.startswith(self.remote.path):
            self.remote.refresh(quiet=True)

    def _failed(self, message: str) -> None:
        self._end_batch()
        self._set_status(f"Stopped: {message}")
        messagebox.showerror("KaiDrop", f"The transfer stopped: {message}")

    def _end_batch(self) -> None:
        self.sending = not self.jobs.empty()
        self.cancel_button.config(state="normal" if self.sending else "disabled")

    def _cancel(self) -> None:
        self.cancel.set()  # Stops the batch being sent; batches queued after it still go.
        self._set_status("Cancelling…")

    def _clear_finished(self) -> None:
        for iid in self.queue.get_children():
            if self.queue.set(iid, "status") not in ("Waiting", "Sending…"):
                self.queue.delete(iid)

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
