"""Dragging the selected files of one pane onto the other, or back onto a
folder of the same pane (moving them on the server). It starts when the
pointer leaves the list: inside it, dragging selects (panes.FilePane). While dragging, a small label
follows the pointer with what's being moved and where it would land, and the
folder under the pointer lights up."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable

from .panes import FilePane
from .places import file_icon

THRESHOLD = 8        # Pixels the pointer moves before a press becomes a drag.
GHOST_OFFSET = (18, 14)
GHOST_BG, GHOST_TEXT, GHOST_DIM = "#2b2b33", "#ffffff", "#b8b8c4"
DROP_BG = "#cfe3ff"


@dataclass(frozen=True)
class Target:
    """A pane the selection can be dropped on. destination(folder_row) names
    where a drop would go: the pane's folder named by the row under the
    pointer, or (None) the folder it shows. on_drop(folder_row) does it.
    can_drop() says whether dropping is possible. folders_only: only on a
    folder row (the source's own pane: the folder it shows is where they are)."""
    pane: FilePane
    verb: str
    destination: Callable[[str | None], str]
    on_drop: Callable[[str | None], None]
    can_drop: Callable[[], bool] = lambda: True
    folders_only: bool = False


class Drag:
    """Drags the source pane's selection onto any of the targets."""

    def __init__(self, root: tk.Misc, source: FilePane, targets: list[Target]) -> None:
        self.root, self.source, self.targets = root, source, targets
        self._start: tuple[int, int] | None = None
        self.dragging = False
        self._lit: tuple[FilePane, str] | None = None
        self._ghost: tk.Toplevel | None = None
        for t in targets:
            t.pane.tree.tag_configure("drop", background=DROP_BG)
        tree = source.tree
        tree.bind("<ButtonPress-1>", self._press, add="+")
        tree.bind("<B1-Motion>", self._motion, add="+")
        tree.bind("<ButtonRelease-1>", self._release, add="+")
        tree.bind("<Escape>", lambda e: self._stop(), add="+")

    # --- The label by the pointer ---

    def _make_ghost(self) -> None:
        ghost = tk.Toplevel(self.root)
        ghost.overrideredirect(True)
        ghost.attributes("-topmost", True)
        try:
            ghost.attributes("-alpha", 0.93)
        except tk.TclError:
            pass  # Not every window system fades windows.
        frame = tk.Frame(ghost, bg=GHOST_BG, padx=10, pady=6)
        frame.pack()
        selected = self.source.selected()
        if len(selected) == 1:
            name, is_dir = selected[0]
            icon, text = self.source.icons["folder" if is_dir else file_icon(name)], name
        else:
            icon, text = self.source.icons["file"], f"{len(selected)} items"
        self._title = tk.Label(frame, image=icon, compound="left", text=f"  {text}", bg=GHOST_BG, fg=GHOST_TEXT,
                               font=("Segoe UI", 10, "bold"))
        self._title.pack(anchor="w")
        self._where = tk.Label(frame, bg=GHOST_BG, fg=GHOST_DIM, font=("Segoe UI", 9))
        self._where.pack(anchor="w")
        self._ghost = ghost

    def _place_ghost(self, x_root: int, y_root: int, where: str, ok: bool) -> None:
        if not self._ghost:
            return
        self._where.config(text=where, fg=GHOST_TEXT if ok else GHOST_DIM)
        self._ghost.geometry(f"+{x_root + GHOST_OFFSET[0]}+{y_root + GHOST_OFFSET[1]}")

    # --- The folder under the pointer ---

    def _folder_under(self, x_root: int, y_root: int) -> tuple[Target | None, str | None, str]:
        """The target under the pointer (None if it's over none it can drop
        on), the folder row under it (None for the list's own folder) and
        that row's id ("" for none)."""
        widget = self.root.winfo_containing(x_root, y_root)
        for target in self.targets:
            tree = target.pane.tree
            if widget is not tree:
                continue
            iid = tree.identify_row(y_root - tree.winfo_rooty())
            entry = target.pane.entries.get(iid)
            is_folder = bool(entry and entry[1])
            if target.folders_only and (not is_folder or iid in tree.selection()):
                continue  # Not a folder, or one of those being dragged.
            return (target, entry[0], iid) if is_folder else (target, None, "")
        return None, None, ""

    def _light(self, pane: FilePane | None, iid: str) -> None:
        lit = (pane, iid) if pane and iid else None
        if lit == self._lit:
            return
        if self._lit and self._lit[0].tree.exists(self._lit[1]):
            self._lit[0].tree.item(self._lit[1], tags=())
        if lit:
            pane.tree.item(iid, tags=("drop",))
        self._lit = lit

    # --- Events ---

    def _press(self, event: tk.Event) -> None:
        self._start = (event.x_root, event.y_root)
        self.dragging = False

    def _motion(self, event: tk.Event) -> None:
        if not self._start:
            return
        if not self.dragging:
            moved = abs(event.x_root - self._start[0]) + abs(event.y_root - self._start[1])
            if moved <= THRESHOLD or not self.source.selected():
                return
            if self.root.winfo_containing(event.x_root, event.y_root) is self.source.tree:
                return  # Up and down in its own list selects (panes.FilePane); out of it, files go.
            self.dragging = True
            self._make_ghost()
            self.root.config(cursor="hand2")
        target, folder, iid = self._folder_under(event.x_root, event.y_root)
        ok = target is not None and target.can_drop()
        self._light(target.pane if ok else None, iid)
        where = f"{target.verb} to {target.destination(folder)}" if ok else "Drop it on the other side or a folder"
        self._place_ghost(event.x_root, event.y_root, where, ok)

    def _release(self, event: tk.Event) -> None:
        dragging = self.dragging
        target, folder, _ = self._folder_under(event.x_root, event.y_root) if dragging else (None, None, "")
        self._stop()
        if dragging and target is not None and target.can_drop():
            target.on_drop(folder)

    def _stop(self) -> None:
        self._start = None
        self.dragging = False
        self._light(None, "")
        if self._ghost:
            self._ghost.destroy()
            self._ghost = None
        self.root.config(cursor="")
