"""Moving and copying on the server itself (cut, copy and paste, or dragging
onto a folder). Moving is FTP's rename, at once. FTP has no copy: a copy
comes down to this computer and goes back up, a file at a time, through a
temporary file."""
from __future__ import annotations

import ftplib
import posixpath
import tempfile
from pathlib import Path
from typing import Callable

from .ftp import free_name
from .remote import check_depth, list_dir

Item = tuple[str, bool]  # Path on the server, and whether it's a folder.
StepFn = Callable[[str], None]  # What's being done now, for the status line.


def inside(path: str, folder: str) -> bool:
    """True if path is folder or somewhere in it."""
    path, folder = path.rstrip("/") or "/", folder.rstrip("/") or "/"
    return path == folder or path.startswith(folder if folder.endswith("/") else folder + "/")


def _names(ftp: ftplib.FTP, folder: str) -> set[str]:
    return {e.name for e in list_dir(ftp, folder)}


def _target(ftp_names: set[str], folder: str, name: str) -> str:
    """folder/name, or "name (2)"… when that's taken."""
    wanted = posixpath.join(folder, name)
    if name not in ftp_names:
        return wanted
    return free_name(wanted, lambda candidate: posixpath.basename(candidate) in ftp_names)


def move_items(ftp: ftplib.FTP, items: list[Item], folder: str) -> list[str]:
    """Moves items into folder. Returns notes for what wasn't moved as is:
    a folder into itself, something already there (skipped), a new name."""
    notes: list[str] = []
    names = _names(ftp, folder)
    for path, is_dir in items:
        name = posixpath.basename(path.rstrip("/"))
        if is_dir and inside(folder, path):
            notes.append(f"“{name}” can't go into itself.")
            continue
        if posixpath.dirname(path.rstrip("/")) == (folder.rstrip("/") or "/"):
            continue  # Already there.
        target = _target(names, folder, name)
        ftp.rename(path, target)
        names.add(posixpath.basename(target))
        if posixpath.basename(target) != name:
            notes.append(f"“{name}” was already there: moved as “{posixpath.basename(target)}”.")
    return notes


def _copy_file(ftp: ftplib.FTP, source: str, target: str, scratch: Path) -> None:
    temp = scratch / "copy.part"
    with temp.open("wb") as f:
        ftp.retrbinary(f"RETR {source}", f.write)
    with temp.open("rb") as f:
        ftp.storbinary(f"STOR {target}", f)
    temp.unlink()


def _copy_tree(ftp: ftplib.FTP, source: str, target: str, scratch: Path, on_step: StepFn, depth: int = 0) -> None:
    check_depth(depth)
    ftp.mkd(target)
    for entry in list_dir(ftp, source):
        child_source, child_target = posixpath.join(source, entry.name), posixpath.join(target, entry.name)
        if entry.is_dir:
            _copy_tree(ftp, child_source, child_target, scratch, on_step, depth + 1)
        else:
            on_step(f"Copying {child_source}…")
            _copy_file(ftp, child_source, child_target, scratch)


def copy_items(ftp: ftplib.FTP, items: list[Item], folder: str, on_step: StepFn = lambda _: None) -> list[str]:
    """Copies items into folder (a copy in the same folder gets a new name).
    Returns notes, as move_items."""
    notes: list[str] = []
    names = _names(ftp, folder)
    with tempfile.TemporaryDirectory(prefix="kaidrop-") as scratch:
        for path, is_dir in items:
            name = posixpath.basename(path.rstrip("/"))
            if is_dir and inside(folder, path):
                notes.append(f"“{name}” can't be copied into itself.")
                continue
            target = _target(names, folder, name)
            names.add(posixpath.basename(target))
            on_step(f"Copying {path}…")
            if is_dir:
                _copy_tree(ftp, path, target, Path(scratch), on_step)
            else:
                _copy_file(ftp, path, target, Path(scratch))
            if posixpath.basename(target) != name:
                notes.append(f"“{name}” was already there: copied as “{posixpath.basename(target)}”.")
    return notes
