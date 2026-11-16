"""The places this computer's folder tree starts from: the user's main
folders and the drives, named the way Explorer names them."""
from __future__ import annotations

import os
import string
import sys
from dataclasses import dataclass
from pathlib import Path

AUDIO = {".mp3", ".flac", ".ogg", ".opus", ".wav", ".m4a", ".aac", ".wma", ".aif", ".aiff",
         ".ape", ".wv", ".dsf", ".dff", ".mka", ".alac"}
IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}

# Windows' known folders: their GUIDs, so moved ones (to OneDrive, another drive) are found.
_KNOWN = [
    ("Desktop", "desktop", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"),
    ("Documents", "documents", "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"),
    ("Downloads", "downloads", "{374DE290-123F-4565-9164-39C4925E467B}"),
    ("Music", "music", "{4BD8D571-6D19-48D3-BE97-422220080E43}"),
]

# GetDriveTypeW
_REMOVABLE, _REMOTE, _CDROM = 2, 4, 5


@dataclass(frozen=True)
class Place:
    label: str
    path: Path
    icon: str


def file_icon(name: str) -> str:
    """The icon for a file: audio, image or a plain file."""
    ext = os.path.splitext(name)[1].lower()
    return "audio" if ext in AUDIO else "image" if ext in IMAGE else "file"


def drive_label(root: str, volume: str, kind: int = 3) -> str:
    """'Datos (D:)', or Explorer's name for a drive without one.

    >>> drive_label("C:\\\\", "")
    'Local Disk (C:)'
    """
    letter = root[:2]
    if not volume:
        volume = {_REMOVABLE: "USB Drive", _REMOTE: "Network Drive", _CDROM: "CD Drive"}.get(kind, "Local Disk")
    return f"{volume} ({letter})"


def is_inside(path: Path, folder: Path) -> bool:
    """True if path is folder or somewhere in it (ignoring case on Windows)."""
    norm = os.path.normcase
    p, f = norm(str(path)), norm(str(folder)).rstrip("\\/")
    return p == f or p.startswith(f + os.sep)


def known_folders() -> list[Place]:
    """Desktop, Documents, Downloads and Music, where they exist."""
    places = []
    for label, icon, guid in _KNOWN:
        path = _known_folder(guid) or Path.home() / label
        if path.is_dir():
            places.append(Place(label, path, icon))
    return places


def drives() -> list[Place]:
    """The drives (C:, D:…) with their names; on macOS and Linux, the root."""
    if sys.platform != "win32":
        return [Place("Computer", Path("/"), "drive")]
    import ctypes
    kernel = ctypes.windll.kernel32
    old_mode = kernel.SetErrorMode(1)  # No "insert a disk" dialogs for empty card readers.
    try:
        mask = kernel.GetLogicalDrives()
        places = []
        for i, letter in enumerate(string.ascii_uppercase):
            if not mask & (1 << i):
                continue
            root = f"{letter}:\\"
            name = ctypes.create_unicode_buffer(261)
            if not kernel.GetVolumeInformationW(root, name, 261, None, None, None, None, 0):
                continue  # No disk in it.
            places.append(Place(drive_label(root, name.value, kernel.GetDriveTypeW(root)), Path(root), "drive"))
        return places
    finally:
        kernel.SetErrorMode(old_mode)


def _known_folder(guid: str) -> Path | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    g = GUID()
    if ctypes.windll.ole32.CLSIDFromString(guid, ctypes.byref(g)) != 0:
        return None
    out = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return Path(out.value) if out.value else None
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)
