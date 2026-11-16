"""This computer's folders as a tree, like Explorer's: the user's main folders
and the drives at the top, and each folder's subfolders read when it opens."""
from __future__ import annotations

import os
import stat
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from .places import Place, drives, is_inside, known_folders

ROOT = "pc"
_PLACEHOLDER = "…"
_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)


def subfolders(folder: Path) -> list[Path]:
    """The folders in a folder, by name, without hidden or system ones."""
    found = []
    try:
        with os.scandir(folder) as items:
            for item in items:
                try:
                    if not item.is_dir() or item.name.startswith((".", "$")):
                        continue
                    if getattr(item.stat(), "st_file_attributes", 0) & _HIDDEN:
                        continue
                except OSError:
                    continue
                found.append(Path(item.path))
    except OSError:
        return []
    return sorted(found, key=lambda p: p.name.lower())


class FolderTree(ttk.Frame):
    """Calls on_open(path) when the user picks a folder; reveal(path) shows
    the folder the list is in."""

    def __init__(self, master: tk.Misc, icons: dict[str, tk.PhotoImage], on_open: Callable[[str], None]) -> None:
        super().__init__(master)
        self.icons = icons
        self.on_open = on_open
        self.tree = ttk.Treeview(self, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.paths: dict[str, Path] = {}  # Node id: its folder.
        self._revealing = False
        self.tree.bind("<<TreeviewOpen>>", lambda e: self._fill(self.tree.focus()))
        self.tree.bind("<<TreeviewSelect>>", self._picked)
        self.reload()

    def reload(self) -> None:
        """Reads the places again (a USB drive plugged in, say)."""
        self.tree.delete(*self.tree.get_children())
        self.paths.clear()
        self.tree.insert("", "end", iid=ROOT, text=" This computer", image=self.icons["computer"], open=True)
        for place in known_folders() + drives():
            self._add(ROOT, place)

    def _add(self, parent: str, place: Place) -> str:
        iid = self.tree.insert(parent, "end", text=f" {place.label}", image=self.icons[place.icon])
        self.paths[iid] = place.path
        self.tree.insert(iid, "end", text=_PLACEHOLDER)  # So it shows an arrow until opened.
        return iid

    def _fill(self, iid: str) -> None:
        """Reads a folder's subfolders the first time it opens."""
        children = self.tree.get_children(iid)
        if iid not in self.paths or len(children) != 1 or self.tree.item(children[0], "text") != _PLACEHOLDER:
            return
        self.tree.delete(children[0])
        for folder in subfolders(self.paths[iid]):
            self._add(iid, Place(folder.name, folder, "folder"))

    def _picked(self, _event: tk.Event) -> None:
        sel = self.tree.selection()
        if self._revealing or not sel or sel[0] not in self.paths:
            return
        self.on_open(str(self.paths[sel[0]]))

    def reveal(self, path: Path) -> None:
        """Opens the tree down to path and selects it, from the closest place
        (Music before C:, for a folder in Music)."""
        places = [iid for iid in self.tree.get_children(ROOT) if is_inside(path, self.paths[iid])]
        if not places:
            return
        node = max(places, key=lambda iid: len(str(self.paths[iid])))
        while os.path.normcase(str(self.paths[node])) != os.path.normcase(str(path)):
            self._fill(node)
            self.tree.item(node, open=True)
            inner = [c for c in self.tree.get_children(node) if c in self.paths and is_inside(path, self.paths[c])]
            if not inner:
                break  # A hidden folder, say: stop at the closest one shown.
            node = inner[0]
        self._revealing = True
        try:
            self.tree.selection_set(node)
            self.tree.see(node)
        finally:
            self.after_idle(self._done_revealing)

    def _done_revealing(self) -> None:
        self._revealing = False
