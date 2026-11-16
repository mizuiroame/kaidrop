"""KaiDrop's window: where to send, what to send, and the upload itself."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, settings
from .ftp import Connection, Status, test_connection, upload
from .plan import Plan, build_plan

POLL_MS = 80
EXPLANATION = (
    "Switch 2 hides files and folders whose names have accents (á, ñ…) or other non-ASCII characters "
    "(like Japanese): they are saved but no app can list them. With this option on, the copies on the "
    "console get plain names. Your files here are never renamed, and players such as KaiPlayer still "
    "show the real titles from the tags."
)


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


class KaiDrop(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"KaiDrop {__version__}")
        self.minsize(880, 600)
        self.saved = settings.load()
        self.sources: list[Path] = []
        self.plan = Plan((), ())
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self._build()
        self._refresh_plan()
        self.after(POLL_MS, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # --- Layout ---

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 6}
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        conn = ttk.LabelFrame(self, text="Console (OunceShell FTP)")
        conn.pack(fill="x", **pad)
        self.host = tk.StringVar(value=self.saved.host)
        self.port = tk.StringVar(value=str(self.saved.port))
        self.user = tk.StringVar(value=self.saved.user)
        self.password = tk.StringVar()
        for col, (label, var, width, show) in enumerate(
            [("IP address", self.host, 16, ""), ("Port", self.port, 6, ""), ("User", self.user, 12, ""),
             ("Password", self.password, 12, "•")]):
            ttk.Label(conn, text=label).grid(row=0, column=col * 2, sticky="w", padx=(10, 4), pady=8)
            ttk.Entry(conn, textvariable=var, width=width, show=show).grid(row=0, column=col * 2 + 1, sticky="w")
        self.test_button = ttk.Button(conn, text="Test connection", command=self._test)
        self.test_button.grid(row=0, column=8, padx=10)

        dest = ttk.LabelFrame(self, text="Send to (folder on the SD card)")
        dest.pack(fill="x", **pad)
        self.remote = tk.StringVar(value=self.saved.remote_folder)
        ttk.Entry(dest, textvariable=self.remote, width=40).pack(side="left", padx=10, pady=8)
        self.remote.trace_add("write", lambda *_: self._refresh_plan())
        self.plain = tk.BooleanVar(value=self.saved.plain_names)
        ttk.Checkbutton(dest, text="Plain names for Switch 2 (recommended)", variable=self.plain,
                        command=self._refresh_plan).pack(side="left", padx=10)

        info = ttk.Label(self, text=EXPLANATION, wraplength=840, foreground="#555")
        info.pack(fill="x", padx=14)

        files = ttk.LabelFrame(self, text="What to send")
        files.pack(fill="both", expand=True, **pad)
        bar = ttk.Frame(files)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Add folder…", command=self._add_folder).pack(side="left")
        ttk.Button(bar, text="Add files…", command=self._add_files).pack(side="left", padx=6)
        ttk.Button(bar, text="Clear", command=self._clear).pack(side="left")
        self.summary = ttk.Label(bar, text="")
        self.summary.pack(side="right")

        columns = ("local", "remote", "size", "status")
        self.tree = ttk.Treeview(files, columns=columns, show="headings", selectmode="none")
        for name, title, width in [("local", "On this computer", 300), ("remote", "On the console", 360),
                                   ("size", "Size", 80), ("status", "Status", 100)]:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, anchor="e" if name == "size" else "w")
        self.tree.tag_configure("renamed", foreground="#a0408c")
        self.tree.tag_configure("failed", foreground="#c0392b")
        scroll = ttk.Scrollbar(files, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        scroll.pack(side="right", fill="y", pady=(0, 8), padx=(0, 8))

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x", side="top", pady=(0, 6))
        self.status = ttk.Label(bottom, text="Add a folder or files to send.")
        self.status.pack(side="left")
        self.cancel_button = ttk.Button(bottom, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(side="right")
        self.send_button = ttk.Button(bottom, text="Send to the console", command=self._send)
        self.send_button.pack(side="right", padx=6)

    # --- Choosing what to send ---

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose a folder to send")
        if folder:
            self._add([Path(folder)])

    def _add_files(self) -> None:
        names = filedialog.askopenfilenames(title="Choose files to send")
        self._add([Path(n) for n in names])

    def _add(self, paths: list[Path]) -> None:
        for path in paths:
            if path not in self.sources:
                self.sources.append(path)
        self._refresh_plan()

    def _clear(self) -> None:
        if not self.busy:
            self.sources.clear()
            self._refresh_plan()

    def _refresh_plan(self) -> None:
        if self.busy:
            return
        self.plan = build_plan(self.sources, self.remote.get(), self.plain.get())
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.plan.items):
            local = Path(*item.local.parts[-2:])  # Its folder and name: enough to recognize it.
            self.tree.insert("", "end", iid=str(i), values=(str(local), item.remote, _size(item.size), ""),
                             tags=("renamed",) if item.renamed else ())
        renamed = self.plan.renamed_count
        text = f"{len(self.plan.items)} files, {_size(self.plan.total_bytes)}"
        if renamed:
            text += f" · {renamed} renamed on the console"
        self.summary.config(text=text if self.plan.items else "")
        self.status.config(text="Ready to send." if self.plan.items else "Add a folder or files to send.")

    # --- Connection and upload (on a thread; results come back through events) ---

    def _connection(self) -> Connection | None:
        host = self.host.get().strip()
        if not host:
            messagebox.showwarning("KaiDrop", "Type the console's IP address, as OunceShell's FTP screen shows it.")
            return None
        if not self.port.get().strip().isdigit():
            messagebox.showwarning("KaiDrop", "The port is a number, as OunceShell's FTP screen shows it.")
            return None
        return Connection(host, int(self.port.get()), self.user.get().strip() or "anonymous", self.password.get())

    def _remember(self) -> None:
        settings.save(settings.Settings(self.host.get().strip(), int(self.port.get() or 5000),
                                        self.user.get().strip() or "anonymous", self.remote.get(), self.plain.get()))

    def _test(self) -> None:
        conn = self._connection()
        if not conn:
            return
        self.test_button.config(state="disabled")
        self.status.config(text="Connecting…")

        def work() -> None:
            try:
                self.events.put(("tested", test_connection(conn)))
            except Exception as e:  # Any failure is shown to the user.
                self.events.put(("test_failed", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _send(self) -> None:
        conn = self._connection()
        if not conn or self.busy:
            return
        if not self.plan.items:
            messagebox.showinfo("KaiDrop", "Add a folder or files first.")
            return
        self._remember()
        self.busy = True
        self.cancel.clear()
        self.send_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.progress.config(maximum=max(self.plan.total_bytes, 1), value=0)
        for iid in self.tree.get_children():
            self.tree.set(iid, "status", "")
        plan = self.plan

        def work() -> None:
            try:
                counts = upload(conn, plan,
                                lambda i, item, sent, total: self.events.put(("progress", i, total)),
                                lambda i, item, status, msg: self.events.put(("done", i, status, msg)),
                                self.cancel)
                self.events.put(("finished", counts))
            except Exception as e:  # Connection errors end the upload with a message.
                self.events.put(("failed", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _handle(self, event: tuple) -> None:
        kind = event[0]
        if kind == "tested":
            self.test_button.config(state="normal")
            self.status.config(text="Connected. " + event[1][:80])
            self._remember()
        elif kind == "test_failed":
            self.test_button.config(state="normal")
            self.status.config(text="Could not connect.")
            messagebox.showerror("KaiDrop", f"Could not connect: {event[1]}\n\nCheck that OunceShell's FTP server "
                                            "is running and the IP address and port match its screen.")
        elif kind == "progress":
            _, index, total = event
            self.progress.config(value=total)
            self.status.config(text=f"Sending {index + 1} of {len(self.plan.items)}…  {_size(total)} of "
                                    f"{_size(self.plan.total_bytes)}")
        elif kind == "done":
            _, index, status, message = event
            self.tree.set(str(index), "status", status.value)
            if status is Status.FAILED:
                self.tree.item(str(index), tags=("failed",))
                self.tree.set(str(index), "status", f"Failed: {message}"[:40])
            self.tree.see(str(index))
        elif kind in ("finished", "failed"):
            self.busy = False
            self.send_button.config(state="normal")
            self.cancel_button.config(state="disabled")
            if kind == "failed":
                self.status.config(text="Stopped.")
                messagebox.showerror("KaiDrop", f"The upload stopped: {event[1]}")
                return
            counts = event[1]
            self.status.config(text=f"Done: {counts[Status.SENT]} sent, {counts[Status.SKIPPED]} already there, "
                                    f"{counts[Status.FAILED]} failed, {counts[Status.CANCELLED]} cancelled.")

    def _close(self) -> None:
        if self.busy and not messagebox.askyesno("KaiDrop", "An upload is running. Stop it and quit?"):
            return
        self.cancel.set()
        self.destroy()


def main() -> None:
    KaiDrop().mainloop()
