"""The window that asks what to do with a file that's already where another
is going, like FileZilla's: both side by side, then skip, replace, keep both
or cancel. Sending, the file already there is on the server; receiving, it's
on this computer."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk

from .ftp import Choice
from .panes import human_size


@dataclass(frozen=True)
class Side:
    label: str                 # "On the server", "Being sent"…
    name: str
    size: int
    modified: datetime | None  # None when unknown.


def _size(n: int) -> str:
    return f"{human_size(n)} ({n:,} bytes)" if n >= 1024 else f"{n:,} bytes"


def _when(stamp: datetime | None) -> str:
    return stamp.strftime("%Y-%m-%d %H:%M") if stamp else "—"


def comparison(existing: Side, incoming: Side) -> str:
    """A short note on how the two differ, for the window."""
    if existing.size == incoming.size:
        return "Both are the same size: probably the same file."
    bigger = existing if existing.size > incoming.size else incoming
    return f"They are different sizes: the one {bigger.label.lower()} is bigger."


class ConflictDialog(tk.Toplevel):
    """Modal. ask() returns the choice and whether it goes for the rest of the batch.
    where: "on the server" or "on this computer"; folder: where the file is."""

    def __init__(self, master: tk.Misc, where: str, folder: str, existing: Side, incoming: Side) -> None:
        super().__init__(master)
        self.title(f"File already {where}")
        self.resizable(False, False)
        self.transient(master)
        self.result: tuple[Choice, bool] = (Choice.CANCEL, False)
        self.for_all = tk.BooleanVar(value=False)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"There's already a file with this name {where}.",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text=folder, foreground="#666").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

        ttk.Label(body, text=existing.label, font=("Segoe UI", 10, "bold")).grid(row=2, column=1, sticky="w")
        ttk.Label(body, text=incoming.label, font=("Segoe UI", 10, "bold")).grid(row=2, column=2, sticky="w",
                                                                                  padx=(24, 0))
        rows = [("Name", existing.name, incoming.name),
                ("Size", _size(existing.size), _size(incoming.size)),
                ("Modified", _when(existing.modified), _when(incoming.modified))]
        for r, (label, there, coming) in enumerate(rows, start=3):
            ttk.Label(body, text=label, foreground="#666").grid(row=r, column=0, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(body, text=there, wraplength=260).grid(row=r, column=1, sticky="w", pady=2)
            ttk.Label(body, text=coming, wraplength=260).grid(row=r, column=2, sticky="w", padx=(24, 0), pady=2)
        ttk.Label(body, text=comparison(existing, incoming)).grid(row=6, column=0, columnspan=3, sticky="w",
                                                                  pady=(10, 4))
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
        ttk.Label(body, text="Keep both saves the new file as “name (2)”.", foreground="#666").grid(
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
