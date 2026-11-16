"""The two file panes: this computer on the left, the server on the right."""
from __future__ import annotations

import os
import posixpath
import string
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from .remote import RemoteEntry, RemoteSession, delete_tree, list_dir, parent

FOLDER = "\U0001F4C1"
FILE = "\U0001F4C4"


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


class FilePane(ttk.Frame):
    """A title, a path bar with Up and Refresh, and a list of entries."""

    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master)
        ttk.Label(self, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=4, pady=(0, 4))
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.path_var = tk.StringVar()
        self.tools = ttk.Frame(bar)
        self.tools.pack(side="right")
        ttk.Button(bar, text="↑", width=3, command=self.go_up).pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.path_var)
        entry.pack(side="left", fill="x", expand=True, padx=4)
        entry.bind("<Return>", lambda e: self.open_path(self.path_var.get()))
        ttk.Button(self.tools, text="⟳", width=3, command=self.refresh).pack(side="left")

        self.tree = ttk.Treeview(self, columns=("size",), selectmode="extended")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=280)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, pady=(4, 0))
        scroll.pack(side="right", fill="y", pady=(4, 0))
        self.tree.bind("<Double-1>", lambda e: self._open_selected())
        self.tree.bind("<Return>", lambda e: self._open_selected())
        self.tree.bind("<BackSpace>", lambda e: self.go_up())
        self.entries: dict[str, tuple[str, bool]] = {}  # Row id: (name, is folder).

    def show(self, rows: list[tuple[str, bool, int]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.entries.clear()
        for i, (name, is_dir, size) in enumerate(rows):
            iid = str(i)
            self.entries[iid] = (name, is_dir)
            self.tree.insert("", "end", iid=iid, text=f"{FOLDER if is_dir else FILE}  {name}",
                             values=("" if is_dir else human_size(size),))

    def selected(self) -> list[tuple[str, bool]]:
        return [self.entries[iid] for iid in self.tree.selection() if iid in self.entries]

    def row_at(self, y: int) -> tuple[str, bool] | None:
        iid = self.tree.identify_row(y)
        return self.entries.get(iid)

    def _open_selected(self) -> None:
        sel = self.selected()
        if len(sel) == 1 and sel[0][1]:
            self.open_child(sel[0][0])

    # Implemented by each side.
    def open_path(self, path: str) -> None: ...
    def open_child(self, name: str) -> None: ...
    def go_up(self) -> None: ...
    def refresh(self) -> None: ...


class LocalPane(FilePane):
    def __init__(self, master: tk.Misc, start: str) -> None:
        super().__init__(master, "This computer")
        if sys.platform == "win32":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            self.drive = ttk.Combobox(self.tools, values=drives, width=5, state="readonly")
            self.drive.pack(side="left", padx=(4, 0))
            self.drive.bind("<<ComboboxSelected>>", lambda e: self.open_path(self.drive.get()))
        self.path = Path(start) if start and Path(start).is_dir() else Path.home()
        self.open_path(str(self.path))

    def open_path(self, path: str) -> None:
        target = Path(path).expanduser()
        try:
            items = list(os.scandir(target))
        except OSError as e:
            messagebox.showerror("KaiDrop", f"Can't open {target}:\n{e}")
            self.path_var.set(str(self.path))
            return
        self.path = target
        self.path_var.set(str(target))
        if hasattr(self, "drive"):
            self.drive.set(target.anchor)
        rows = []
        for item in items:
            try:
                is_dir = item.is_dir()
                rows.append((item.name, is_dir, 0 if is_dir else item.stat().st_size))
            except OSError:
                continue  # Unreadable entry: leave it out.
        rows.sort(key=lambda r: (not r[1], r[0].lower()))
        self.show(rows)

    def open_child(self, name: str) -> None:
        self.open_path(str(self.path / name))

    def go_up(self) -> None:
        if self.path.parent != self.path:
            self.open_path(str(self.path.parent))

    def refresh(self) -> None:
        self.open_path(str(self.path))

    def selected_paths(self) -> list[Path]:
        return [self.path / name for name, _ in self.selected()]


class RemotePane(FilePane):
    """The server's folders. Every network call goes through the session."""

    def __init__(self, master: tk.Misc, start: str, on_status: Callable[[str], None]) -> None:
        super().__init__(master, "Server (the console)")
        ttk.Button(self.tools, text="New folder", command=self._new_folder).pack(side="left", padx=(4, 0))
        ttk.Button(self.tools, text="Delete", command=self._delete).pack(side="left", padx=(4, 0))
        self.session: RemoteSession | None = None
        self.path = start or "/"
        self.path_var.set(self.path)
        self.on_status = on_status
        self.show([])

    def attach(self, session: RemoteSession | None) -> None:
        self.session = session
        if session:
            self.open_path(self.path)
        else:
            self.show([])

    def open_path(self, path: str, quiet: bool = False) -> None:
        """quiet: leave the status line alone (a refresh after a transfer)."""
        if not self.session:
            self.on_status("Connect to the server first.")
            return
        path = "/" + path.strip("/") if path.strip("/") else "/"
        if not quiet:
            self.on_status(f"Listing {path}…")

        def shown(entries: list[RemoteEntry]) -> None:
            self.path = path
            self.path_var.set(path)
            self.show([(e.name, e.is_dir, e.size) for e in entries])
            if not quiet:
                self.on_status(f"{len(entries)} items in {path}")

        def failed(message: str) -> None:
            self.path_var.set(self.path)
            self.on_status(f"Can't list {path}: {message}")

        self.session.submit(lambda ftp: list_dir(ftp, path), shown, failed)

    def open_child(self, name: str) -> None:
        self.open_path(posixpath.join(self.path, name))

    def go_up(self) -> None:
        self.open_path(parent(self.path))

    def refresh(self, quiet: bool = False) -> None:
        self.open_path(self.path, quiet)

    def _new_folder(self) -> None:
        if not self.session:
            return
        name = simpledialog.askstring("New folder", "Folder name:", parent=self)
        if not name or "/" in name:
            return
        target = posixpath.join(self.path, name)
        self.session.submit(lambda ftp: ftp.mkd(target), lambda _: self.refresh(),
                            lambda m: messagebox.showerror("KaiDrop", f"Can't create {target}:\n{m}"))

    def _delete(self) -> None:
        sel = self.selected()
        if not self.session or not sel:
            return
        names = ", ".join(name for name, _ in sel[:5]) + ("…" if len(sel) > 5 else "")
        if not messagebox.askyesno("KaiDrop", f"Delete from the server?\n\n{names}\n\nFolders are deleted with "
                                              "everything in them. This can't be undone."):
            return
        targets = [(posixpath.join(self.path, name), is_dir) for name, is_dir in sel]

        def work(ftp) -> None:
            for path, is_dir in targets:
                delete_tree(ftp, path, is_dir)

        self.session.submit(work, lambda _: self.refresh(),
                            lambda m: (messagebox.showerror("KaiDrop", f"Couldn't delete everything:\n{m}"),
                                       self.refresh()))
