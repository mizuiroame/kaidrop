"""What to upload where: the files under the chosen folders and files, with
the names they get on the console."""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, replace
from pathlib import Path

from .names import unique_names
from .playlists import PlaylistCopy, is_playlist, local_key, prepare


@dataclass(frozen=True)
class UploadItem:
    local: Path      # The file on this computer.
    remote: str      # Its full path on the console.
    size: int
    renamed: bool    # Its name (or a folder above it) was changed for the console.
    playlist: PlaylistCopy | None = None  # A playlist whose copy points to the songs' names there.

    @property
    def playlist_changes(self) -> int:
        return len(self.playlist.changes) if self.playlist else 0


@dataclass(frozen=True)
class Plan:
    items: tuple[UploadItem, ...]
    folders: tuple[str, ...]   # Remote folders to create, parents first.

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.items)

    @property
    def renamed_count(self) -> int:
        return sum(1 for item in self.items if item.renamed)


def _walk(local: Path, remote: str, plain: bool, renamed: bool, items: list[UploadItem], folders: list[str]) -> None:
    folders.append(remote)
    try:
        entries = sorted(local.iterdir(), key=lambda e: e.name.lower())
    except OSError:
        return  # Unreadable folder: nothing to send from it.
    names = unique_names([e.name for e in entries], {e.name for e in entries if e.is_dir()}, plain)
    for entry in entries:
        target = posixpath.join(remote, names[entry.name])
        changed = renamed or names[entry.name] != entry.name
        if entry.is_dir():
            _walk(entry, target, plain, changed, items, folders)
        elif entry.is_file():
            items.append(UploadItem(entry, target, entry.stat().st_size, changed))


def build_plan(sources: list[Path], remote_root: str, plain: bool = True) -> Plan:
    """Plans uploading each source (a folder, with everything in it, or a
    file) into remote_root. plain: give names the console can list."""
    remote_root = "/" + remote_root.strip("/") if remote_root.strip("/") else "/"
    items: list[UploadItem] = []
    folders: list[str] = [remote_root] if remote_root != "/" else []
    names = unique_names([s.name for s in sources], {s.name for s in sources if s.is_dir()}, plain)
    for source in sorted(sources, key=lambda s: s.name.lower()):
        target = posixpath.join(remote_root, names[source.name])
        changed = names[source.name] != source.name
        if source.is_dir():
            _walk(source, target, plain, changed, items, folders)
        elif source.is_file():
            items.append(UploadItem(source, target, source.stat().st_size, changed))
    return Plan(tuple(_with_playlists(items, plain)), tuple(dict.fromkeys(folders)))


def _with_playlists(items: list[UploadItem], plain: bool) -> list[UploadItem]:
    """Playlists get a copy that points to the songs' names on the console
    (the file on this computer stays as it is)."""
    sent = {local_key(item.local): item.remote for item in items}
    result = []
    for item in items:
        copy = prepare(item.local, item.remote, sent, plain) if is_playlist(item.local) else None
        result.append(replace(item, size=copy.size, playlist=copy) if copy else item)
    return result
