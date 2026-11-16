"""Plain (ASCII) names that the Switch 2 can list.

On Switch 2, a file or folder whose name has characters outside basic ASCII
(accents such as á or ñ, or Japanese) is saved, but directory listings leave
it out, in every app. These functions give each name an ASCII version for the
copy on the console; the files on the computer are never renamed.
"""
from __future__ import annotations

import re
import unicodedata

# Characters that FTP and the console's file system handle in names.
_UNSAFE = re.compile(r"[^A-Za-z0-9 _.,()'&!+\-\[\]]+")

# Typographic punctuation with a plain look-alike.
_PUNCTUATION = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": "'", "”": "'", "„": "'", "«": "'", "»": "'",
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "…": "...", "¿": "", "¡": "",
})


def is_plain(name: str) -> bool:
    """True if the console can list a file or folder with this name."""
    return name.isascii() and not _UNSAFE.search(name)


def _clean(name: str) -> str:
    """Accents dropped, typographic punctuation made plain, the rest as "_"."""
    decomposed = unicodedata.normalize("NFKD", name.translate(_PUNCTUATION))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    clean = _UNSAFE.sub("_", stripped)
    return re.sub(r"_+", "_", clean).strip(" ").rstrip(".")


def ascii_name(name: str) -> str:
    """An ASCII version of a file name: accents dropped, the rest as "_".

    >>> ascii_name("06 Canción.flac")
    '06 Cancion.flac'
    """
    clean = _clean(name)
    stem, dot, ext = clean.rpartition(".")
    if dot and not stem.strip("_ ."):
        clean = "track" + dot + ext  # Nothing readable was left.
    return clean or "untitled"


def folder_name(name: str) -> str:
    """An ASCII version of a folder name (a dot in it is not an extension)."""
    clean = _clean(name)
    return clean if clean.strip("_ .") else "untitled"


def unique_names(names: list[str], folders: set[str] | None = None, plain: bool = True) -> dict[str, str]:
    """Maps each name to its name on the console, unique among its siblings.

    With plain=False, names stay as they are (only made unique).
    Names that differ only in case count as the same: the SD card's file
    system (exFAT or FAT32) ignores case.
    """
    folders = folders or set()
    taken: set[str] = set()
    result: dict[str, str] = {}
    for name in sorted(names, key=str.lower):
        is_folder = name in folders
        candidate = (folder_name(name) if is_folder else ascii_name(name)) if plain else name
        stem, dot, ext = candidate.rpartition(".")
        if not dot or is_folder:
            stem, dot, ext = candidate, "", ""
        n = 2
        while candidate.lower() in taken:
            candidate = f"{stem} ({n}){dot}{ext}"
            n += 1
        taken.add(candidate.lower())
        result[name] = candidate
    return result
