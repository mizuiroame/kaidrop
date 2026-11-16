"""The window that asks what to do with a file already on the server, like
FileZilla's: both files side by side, then skip, replace, keep both or cancel."""
from __future__ import annotations

import posixpath
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .ftp import Choice, RemoteFile
from .panes import human_size
from .plan import UploadItem


def _size(n: int) -> str:
    return f"{human_size(n)} ({n:,} bytes)" if n >= 1024 else f"{n:,} bytes"


def _when(stamp: datetime | None) -> str:
    return stamp.strftime("%Y-%m-%d %H:%M") if stamp else "—"


def comparison(item: UploadItem, remote: RemoteFile) -> str:
    """A short note on how the two differ, for the window."""
    if remote.size == item.size:
        return "Both are the same size: probably the same file."
    bigger = "on the server" if remote.size > item.size else "being sent"
    return f"They are different sizes: the one {bigger} is bigger."


class ConflictDialog(tk.Toplevel):
    """Modal. ask() returns the choice and whether it goes for the rest of the batch."""

    def __init__(self, master: tk.Misc, item: UploadItem, remote: RemoteFile) -> None:
        super().__init__(master)
        self.title("File already on the server")
        self.resizable(False, False)
        self.transient(master)
        self.result: tuple[Choice, bool] = (Choice.CANCEL, False)
        self.for_all = tk.BooleanVar(value=False)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="There's already a file with this name on the server.",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text=posixpath.dirname(remote.path) or "/", foreground="#666").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

        ttk.Label(body, text="On the server", font=("Segoe UI", 10, "bold")).grid(row=2, column=1, sticky="w")
        ttk.Label(body, text="Being sent", font=("Segoe UI", 10, "bold")).grid(row=2, column=2, sticky="w",
                                                                               padx=(24, 0))
        local_modified = datetime.fromtimestamp(item.local.stat().st_mtime) if item.local.exists() else None
        rows = [("Name", posixpath.basename(remote.path), item.local.name),
                ("Size", _size(remote.size), _size(item.size)),
                ("Modified", _when(remote.modified), _when(local_modified))]
        for r, (label, theirs, ours) in enumerate(rows, start=3):
            ttk.Label(body, text=label, foreground="#666").grid(row=r, column=0, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(body, text=theirs, wraplength=260).grid(row=r, column=1, sticky="w", pady=2)
            ttk.Label(body, text=ours, wraplength=260).grid(row=r, column=2, sticky="w", padx=(24, 0), pady=2)
        ttk.Label(body, text=comparison(item, remote)).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 4))
        ttk.Checkbutton(body, text="Do the same for the other files already there in this batch",
                        variable=self.for_all).grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(16, 0))
        for text, choice in [("Skip", Choice.SKIP), ("Replace", Choice.REPLACE),
                             ("Keep both", Choice.KEEP_BOTH), ("Cancel the batch", Choice.CANCEL)]:
            button = ttk.Button(buttons, text=text, command=lambda c=choice: self._choose(c))
            button.pack(side="left", padx=(6, 0))
            if choice is Choice.SKIP:
                button.focus_set()
        ttk.Label(body, text="Keep both sends the new file as “name (2)”.", foreground="#666").grid(
            row=9, column=0, columnspan=3, sticky="e", pady=(6, 0))
        self.bind("<Escape>", lambda e: self._choose(Choice.CANCEL))
        self.protocol("WM_DELETE_WINDOW", lambda: self._choose(Choice.CANCEL))

    def _choose(self, choice: Choice) -> None:
        self.result = (choice, self.for_all.get() and choice is not Choice.CANCEL)
        self.destroy()

    def ask(self) -> tuple[Choice, bool]:
        self.update_idletasks()
        master = self.master
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.wait_window()
        return self.result
