"""The two file panes: this computer on the left, the server on the right."""
from __future__ import annotations

import os
import posixpath
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from .foldertree import FolderTree
from .icons import ICONS
from .names import ascii_name, folder_name, is_plain
from .places import file_icon
from .remote import RemoteEntry, RemoteSession, delete_tree, list_dir, parent
from .serverops import Item, copy_items, move_items

_BAD_LOCAL = set('\\/:*?"<>|')  # Characters Windows doesn't allow in names.
SHIFT, CONTROL = 0x0001, 0x0004   # Event.state bits.
CLICK_SLOP = 8                    # Pixels a press may move and still be a click, not a drag.
AUTOSCROLL_MS = 60                # How often the list scrolls while a drag is past its edge.
_images: dict[str, tk.PhotoImage] = {}

# A context menu entry: a label and its command (None: shown greyed out), or None for a separator.
MenuItem = tuple[str, Callable[[], None] | None] | None


def icon_images() -> dict[str, tk.PhotoImage]:
    """The icons as images, made once (Tk needs a window before it can)."""
    if not _images:
        _images.update({name: tk.PhotoImage(data=data) for name, data in ICONS.items()})
    return _images


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


@dataclass
class _Band:
    """A selection by dragging: the row it began on, the rows kept (Ctrl),
    and how it's going."""
    start: str
    base: tuple[str, ...]
    moved: bool = False    # Past the click slop.
    spanned: bool = False  # Has reached another row: the range is the selection.
    out: bool = False      # Left the list sideways: now a drag of files.
    last_y: int = 0


class FilePane(ttk.Frame):
    """A title, a path bar with Up and Refresh, and a list of entries with a
    right-click menu."""

    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master)
        self.icons = icon_images()
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

        holder = self._list_holder()
        self.tree = ttk.Treeview(holder, columns=("size",), selectmode="extended")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=280)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._open_selected())
        self.tree.bind("<Return>", lambda e: self._open_selected())
        self.tree.bind("<BackSpace>", lambda e: self.go_up())
        self.tree.bind("<F5>", lambda e: self.refresh())
        self.tree.bind("<Button-3>", self._context_menu)
        # Selecting several, as in Explorer: Ctrl+click and Shift+click (Tk's own),
        # Shift+arrows, Shift+Home/End and Ctrl+A, and dragging a selection whole.
        self.tree.bind("<ButtonPress-1>", self._press, add="+")
        # Bound before dragdrop.Drag's: a drag that selects stops here.
        self.tree.bind("<B1-Motion>", self._band_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._release, add="+")
        self.tree.bind("<<TreeviewSelect>>", self._note_anchor, add="+")
        self.tree.bind("<Shift-Up>", lambda e: self.extend_selection(-1))
        self.tree.bind("<Shift-Down>", lambda e: self.extend_selection(1))
        self.tree.bind("<Shift-Prior>", lambda e: self.extend_selection(-10))
        self.tree.bind("<Shift-Next>", lambda e: self.extend_selection(10))
        self.tree.bind("<Shift-Home>", lambda e: self.extend_selection(-len(self.tree.get_children())))
        self.tree.bind("<Shift-End>", lambda e: self.extend_selection(len(self.tree.get_children())))
        self.tree.bind("<Control-a>", lambda e: self.select_all())
        self.tree.bind("<Control-A>", lambda e: self.select_all())
        self.menu = tk.Menu(self, tearoff=0)
        self.entries: dict[str, tuple[str, bool]] = {}  # Row id: (name, is folder).
        self._anchor = ""      # Where a Shift selection starts.
        self._held: tuple[tuple[str, ...], str] | None = None  # A selection kept while a press may become a drag.
        self._press_at = (0, 0)
        self._band: _Band | None = None      # Selecting by dragging.
        self._scroll_job: str | None = None  # Scrolling while the pointer is past an edge.

    def _list_holder(self) -> ttk.Frame:
        """Where the list goes: below the path bar, unless a side puts something there too."""
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True, pady=(4, 0))
        return holder

    def show(self, rows: list[tuple[str, bool, int]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.entries.clear()
        for i, (name, is_dir, size) in enumerate(rows):
            iid = str(i)
            self.entries[iid] = (name, is_dir)
            self.tree.insert("", "end", iid=iid, text=f" {name}",
                             image=self.icons["folder" if is_dir else file_icon(name)],
                             values=("" if is_dir else human_size(size),))

    # --- Selecting several ---

    def _press(self, event: tk.Event) -> None:
        """Pressing in the list starts a selection by dragging: up and down,
        the rows the pointer goes over are selected (added to the others with
        Ctrl), even from a row already selected. Leaving the list sideways
        turns it into a drag of the selected files to the other side
        (dragdrop.Drag). A plain press on a row of a selection of several
        keeps them all (Tk would leave just that row) until the pointer
        reaches another row, so they can be dragged out together; a click
        that doesn't drag leaves just that row on release, as in Explorer."""
        iid = self.tree.identify_row(event.y)
        selection = self.tree.selection()
        self._press_at = (event.x, event.y)
        self._held = None
        self._band = None
        self._stop_scrolling()
        if (self.tree.identify_region(event.x, event.y) == "heading" or event.state & SHIFT
                or not self.tree.get_children()):
            return
        if iid and iid in selection and len(selection) > 1 and not event.state & CONTROL:
            self._held = (selection, iid)
            self.after_idle(self._keep_held)
        base = selection if event.state & CONTROL else ()
        self._band = _Band(iid or self._row_near(event.y), base)

    def _keep_held(self) -> None:
        if self._held:
            self.tree.selection_set(self._held[0])

    def _row_near(self, y: int) -> str:
        """The row at y, or the first or last row in view when y is above or below them."""
        iid = self.tree.identify_row(y)
        if iid:
            return iid
        height = self.tree.winfo_height()
        rows = range(0, height, 4) if y < height // 2 else range(height - 1, -1, -4)
        for row_y in rows:
            iid = self.tree.identify_row(row_y)
            if iid:
                return iid
        items = self.tree.get_children()
        return items[0] if y < height // 2 else items[-1]

    def _height(self, y: int) -> int:
        """The list's height (a stand-in when it isn't on screen: the tests)."""
        return self.tree.winfo_height() if self.tree.winfo_ismapped() else y + 1

    def _band_motion(self, event: tk.Event) -> str | None:
        """Selects from where the drag began to the row under the pointer,
        scrolling while it's past the list's top or bottom."""
        band = self._band
        if not band or band.out:
            return None  # A drag of files: dragdrop.Drag carries it.
        width = self.tree.winfo_width() if self.tree.winfo_ismapped() else event.x + 1
        if event.x < 0 or event.x >= width:
            band.out = True  # Out sideways: the selection goes to the other side.
            self._stop_scrolling()
            return None
        if not band.moved:
            if abs(event.x - self._press_at[0]) + abs(event.y - self._press_at[1]) <= CLICK_SLOP:
                return "break"
            band.moved = True
        band.last_y = event.y
        self._band_select(event.y)
        if (event.y < 0 or event.y >= self._height(event.y)) and self._scroll_job is None:
            self._auto_scroll()
        return "break"

    def _band_select(self, y: int) -> None:
        band = self._band
        items = self.tree.get_children()
        here = self._row_near(max(0, min(y, self._height(y) - 1)))
        if here == band.start and not band.spanned:
            return  # Still on the row it began on: the selection stays as it was.
        band.spanned = True
        self._held = None  # Released, it's this selection that stays.
        low, high = sorted((items.index(band.start), items.index(here)))
        self.tree.selection_set(tuple(dict.fromkeys(band.base + items[low:high + 1])))
        self.tree.focus(here)
        self._anchor = band.start

    def _auto_scroll(self) -> None:
        """While the pointer stays past the top or bottom, the list keeps scrolling."""
        self._scroll_job = None
        band = self._band
        if not band or band.out or 0 <= band.last_y < self._height(band.last_y):
            return
        self.tree.yview_scroll(-1 if band.last_y < 0 else 1, "units")
        self._band_select(band.last_y)
        self._scroll_job = self.after(AUTOSCROLL_MS, self._auto_scroll)

    def _stop_scrolling(self) -> None:
        if self._scroll_job is not None:
            self.after_cancel(self._scroll_job)
            self._scroll_job = None

    def _release(self, event: tk.Event) -> None:
        self._band = None
        self._stop_scrolling()
        held, self._held = self._held, None
        moved = abs(event.x - self._press_at[0]) + abs(event.y - self._press_at[1])
        if held and moved <= CLICK_SLOP:
            self.tree.selection_set(held[1])
            self.tree.focus(held[1])
            self._anchor = held[1]

    def _note_anchor(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if len(selection) == 1:
            self._anchor = selection[0]

    def extend_selection(self, step: int) -> str:
        """Shift+arrow: moves the focus by step rows and selects from the anchor to it."""
        items = self.tree.get_children()
        if not items:
            return "break"
        focus = self.tree.focus() if self.tree.focus() in items else items[0]
        anchor = self._anchor if self._anchor in items else focus
        target = max(0, min(len(items) - 1, items.index(focus) + step))
        low, high = sorted((items.index(anchor), target))
        self.tree.selection_set(items[low:high + 1])
        self.tree.focus(items[target])
        self.tree.see(items[target])
        self._anchor = anchor
        return "break"

    def select_all(self) -> str:
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def selected(self) -> list[tuple[str, bool]]:
        return [self.entries[iid] for iid in self.tree.selection() if iid in self.entries]

    def row_at(self, y: int) -> tuple[str, bool] | None:
        iid = self.tree.identify_row(y)
        return self.entries.get(iid)

    def _open_selected(self) -> None:
        sel = self.selected()
        if len(sel) == 1 and sel[0][1]:
            self.open_child(sel[0][0])

    def _context_menu(self, event: tk.Event) -> None:
        """Like Explorer: a right-click on a row selects it (unless it's already
        among the selected ones); on empty space, nothing is selected."""
        self.tree.focus_set()
        iid = self.tree.identify_row(event.y)
        if not iid:
            self.tree.selection_set(())
        elif iid not in self.tree.selection():
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        self.menu.delete(0, "end")
        for item in self.menu_items():
            if item is None:
                self.menu.add_separator()
            else:
                label, command = item
                self.menu.add_command(label=label, command=command or (lambda: None),
                                      state="normal" if command else "disabled")
        self.menu.tk_popup(event.x_root, event.y_root)

    def _single_folder(self) -> str | None:
        sel = self.selected()
        return sel[0][0] if len(sel) == 1 and sel[0][1] else None

    # Implemented by each side.
    def menu_items(self) -> list[MenuItem]: ...
    def open_path(self, path: str) -> None: ...
    def open_child(self, name: str) -> None: ...
    def go_up(self) -> None: ...
    def refresh(self) -> None: ...


class LocalPane(FilePane):
    """The folder tree above, the folder's contents below, as in FileZilla."""

    def __init__(self, master: tk.Misc, start: str, on_send: Callable[[], None]) -> None:
        self.on_send = on_send
        super().__init__(master, "This computer")
        self.path = Path(start) if start and Path(start).is_dir() else Path.home()
        self.open_path(str(self.path))

    def _list_holder(self) -> ttk.Frame:
        split = ttk.PanedWindow(self, orient="vertical")
        split.pack(fill="both", expand=True, pady=(4, 0))
        self.folders = FolderTree(split, self.icons, self.open_path)
        holder = ttk.Frame(split)
        split.add(self.folders, weight=2)
        split.add(holder, weight=3)
        return holder

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
        rows = []
        for item in items:
            try:
                is_dir = item.is_dir()
                rows.append((item.name, is_dir, 0 if is_dir else item.stat().st_size))
            except OSError:
                continue  # Unreadable entry: leave it out.
        rows.sort(key=lambda r: (not r[1], r[0].lower()))
        self.show(rows)
        self.folders.reveal(target)

    def open_child(self, name: str) -> None:
        self.open_path(str(self.path / name))

    def go_up(self) -> None:
        if self.path.parent != self.path:
            self.open_path(str(self.path.parent))

    def refresh(self) -> None:
        self.open_path(str(self.path))

    def selected_paths(self) -> list[Path]:
        return [self.path / name for name, _ in self.selected()]

    def menu_items(self) -> list[MenuItem]:
        sel = self.selected()
        return [("Send to the server", self.on_send if sel else None),
                ("Open", self._open if len(sel) == 1 else None),
                None,
                ("New folder", self._new_folder),
                ("Refresh", self._refresh_all)]

    def _open(self) -> None:
        """A folder opens here; a file opens in its usual app."""
        name, is_dir = self.selected()[0]
        if is_dir:
            self.open_child(name)
            return
        target = self.path / name
        try:
            if sys.platform == "win32":
                os.startfile(target)  # noqa: S606 (the user's own file, opened on purpose)
            else:
                import subprocess
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])
        except OSError as e:
            messagebox.showerror("KaiDrop", f"Can't open {target}:\n{e}")

    def _new_folder(self) -> None:
        name = simpledialog.askstring("New folder", "Folder name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if _BAD_LOCAL & set(name):
            messagebox.showerror("KaiDrop", 'A folder name can\'t have any of these: \\ / : * ? " < > |')
            return
        try:
            (self.path / name).mkdir()
        except OSError as e:
            messagebox.showerror("KaiDrop", f"Can't create {self.path / name}:\n{e}")
            return
        self._refresh_all()

    def _refresh_all(self) -> None:
        """The list, and the tree (new folders, a drive plugged in)."""
        self.folders.reload()
        self.refresh()


class RemotePane(FilePane):
    """The server's folders. Every network call goes through the session."""

    def __init__(self, master: tk.Misc, start: str, on_status: Callable[[str], None],
                 plain_names: Callable[[], bool], on_download: Callable[[], None]) -> None:
        self.on_download = on_download
        super().__init__(master, "Server (the console)")
        ttk.Button(self.tools, text="New folder", command=self._new_folder).pack(side="left", padx=(4, 0))
        ttk.Button(self.tools, text="Delete", command=self._delete).pack(side="left", padx=(4, 0))
        self.tree.bind("<Delete>", lambda e: self._delete())
        self.tree.bind("<F2>", lambda e: self._rename())
        for key, command in (("x", self._cut), ("c", self._copy), ("v", self.paste)):
            self.tree.bind(f"<Control-{key}>", lambda e, c=command: c())
            self.tree.bind(f"<Control-{key.upper()}>", lambda e, c=command: c())
        self.clipboard: tuple[str, list[Item]] | None = None  # "cut" or "copy", and what.
        self.session: RemoteSession | None = None
        self.path = start or "/"
        self.path_var.set(self.path)
        self.on_status = on_status
        self.plain_names = plain_names
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

    def menu_items(self) -> list[MenuItem]:
        if not self.session:
            return [("Connect to the server first", None)]
        sel = self.selected()
        folder = self._single_folder()
        into = f"Paste into “{folder}”" if folder else "Paste"
        return [("Download to this computer", self.on_download if sel else None),
                ("Open", (lambda: self.open_child(folder)) if folder else None),
                None,
                ("Cut", self._cut if sel else None),
                ("Copy", self._copy if sel else None),
                (into, (lambda: self.paste(posixpath.join(self.path, folder) if folder else None))
                 if self.clipboard else None),
                None,
                ("New folder", self._new_folder),
                ("Rename", self._rename if len(sel) == 1 else None),
                ("Delete", self._delete if sel else None),
                None,
                ("Refresh", self.refresh)]

    def _console_name(self, name: str, is_dir: bool) -> str:
        """With plain names on, a name the Switch 2 can list (it hides the others)."""
        if not self.plain_names() or is_plain(name):
            return name
        plain = folder_name(name) if is_dir else ascii_name(name)
        self.on_status(f"“{name}” would be hidden on Switch 2: named “{plain}” instead.")
        return plain

    def _ask_name(self, title: str, initial: str = "") -> str | None:
        name = simpledialog.askstring(title, "Name:", initialvalue=initial, parent=self)
        if not name or not name.strip():
            return None
        if "/" in name:
            messagebox.showerror("KaiDrop", "A name can't have “/” in it.")
            return None
        return name.strip()

    def _new_folder(self) -> None:
        if not self.session:
            return
        name = self._ask_name("New folder")
        if not name:
            return
        target = posixpath.join(self.path, self._console_name(name, True))
        self.session.submit(lambda ftp: ftp.mkd(target), lambda _: self.refresh(quiet=True),
                            lambda m: messagebox.showerror("KaiDrop", f"Can't create {target}:\n{m}"))

    def _rename(self) -> None:
        sel = self.selected()
        if not self.session or len(sel) != 1:
            return
        old, is_dir = sel[0]
        name = self._ask_name("Rename", old)
        if not name or name == old:
            return
        source = posixpath.join(self.path, old)
        target = posixpath.join(self.path, self._console_name(name, is_dir))
        self.session.submit(lambda ftp: ftp.rename(source, target), lambda _: self.refresh(quiet=True),
                            lambda m: messagebox.showerror("KaiDrop", f"Can't rename {source}:\n{m}"))

    # --- Cut, copy and paste, and moving by dragging ---

    def _selected_items(self) -> list[Item]:
        return [(posixpath.join(self.path, name), is_dir) for name, is_dir in self.selected()]

    def _clip(self, mode: str) -> None:
        items = self._selected_items()
        if not self.session or not items:
            return
        self.clipboard = (mode, items)
        what = f"“{posixpath.basename(items[0][0])}”" if len(items) == 1 else f"{len(items)} items"
        verb = "Cut" if mode == "cut" else "Copied"
        self.on_status(f"{verb} {what}: open another folder and Paste (Ctrl+V).")

    def _cut(self) -> None:
        self._clip("cut")

    def _copy(self) -> None:
        self._clip("copy")

    def paste(self, folder: str | None = None) -> None:
        """Pastes what was cut or copied into folder (or the one shown)."""
        if not self.session or not self.clipboard:
            return
        mode, items = self.clipboard
        target = folder or self.path
        if mode == "cut":
            self.clipboard = None  # Moved once; a second Paste would find nothing.
            self.move_into(items, target)
            return
        if not messagebox.askyesno("KaiDrop", "FTP can't copy on the server itself: KaiDrop downloads each file "
                                              "and sends it back. Big videos take as long as sending them.\n\n"
                                              f"Copy into {target}?"):
            return
        session, status = self.session, self.on_status

        def step(message: str) -> None:
            session.post(lambda m=message: status(m))

        self.on_status(f"Copying into {target}…")
        session.submit(lambda ftp: copy_items(ftp, items, target, step),
                       lambda notes: self._done("Copied", target, notes),
                       lambda m: (messagebox.showerror("KaiDrop", f"Couldn't copy everything:\n{m}"),
                                  self.refresh()))

    def move_into(self, items: list[Item], folder: str) -> None:
        """Moves items into folder on the server (Paste after Cut, or a drag onto a folder)."""
        if not self.session or not items:
            return
        self.on_status(f"Moving into {folder}…")
        self.session.submit(lambda ftp: move_items(ftp, items, folder),
                            lambda notes: self._done("Moved", folder, notes),
                            lambda m: (messagebox.showerror("KaiDrop", f"Couldn't move everything:\n{m}"),
                                       self.refresh()))

    def _done(self, verb: str, folder: str, notes: list[str]) -> None:
        self.refresh(quiet=True)
        self.on_status(" ".join(notes) if notes else f"{verb} to {folder}.")

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
