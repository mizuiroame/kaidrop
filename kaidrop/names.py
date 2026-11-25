"""Plain (ASCII) names that the Switch 2 can list.

On Switch 2, a file or folder whose name has characters outside basic ASCII
(accents such as á or ñ, or Japanese) is saved, but directory listings leave
it out, in every app. These functions give each name an ASCII version for the
copy on the console; the files on the computer are never renamed. Other
alphabets are written in Latin letters (romanize.py): 水色.mp3 -> Mizuiro.mp3.
"""
from __future__ import annotations

import re
import unicodedata

from .romanize import romanize

# The SD card's file systems take 255 characters; room is left for " (2)".
MAX_LENGTH = 240

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


def _clean(name: str, where: str) -> str:
    """Other alphabets in Latin letters, accents dropped, typographic
    punctuation made plain, the rest as "_"."""
    decomposed = unicodedata.normalize("NFKD", romanize(name, where).translate(_PUNCTUATION))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    clean = _UNSAFE.sub("_", stripped)
    return re.sub(r"_+", "_", clean).strip(" ").rstrip(".")


def _shorten(stem: str, ext: str) -> str:
    """At most MAX_LENGTH characters, cut at the end of the stem."""
    room = MAX_LENGTH - len(ext)
    return stem if len(stem) <= room else stem[:room].rstrip(" ._")


def ascii_name(name: str, where: str = "") -> str:
    """An ASCII version of a file name: other alphabets in Latin letters,
    accents dropped, the rest as "_". where: the folder the file is in on
    this computer, which tells Japanese kanji from Chinese.

    >>> ascii_name("06 Canción.flac")
    '06 Cancion.flac'
    """
    clean = _clean(name, where)
    stem, dot, ext = clean.rpartition(".")
    if not dot:
        stem, ext = clean, ""
    if dot and not stem.strip("_ ."):
        stem = "track"  # Nothing readable was left.
    clean = _shorten(stem, dot + ext) + dot + ext
    return clean or "untitled"


def folder_name(name: str, where: str = "") -> str:
    """An ASCII version of a folder name (a dot in it is not an extension)."""
    clean = _shorten(_clean(name, where), "")
    return clean if clean.strip("_ .") else "untitled"


def unique_names(names: list[str], folders: set[str] | None = None, plain: bool = True,
                 where: str = "") -> dict[str, str]:
    """Maps each name to its name on the console, unique among its siblings.

    With plain=False, names stay as they are (only made unique).
    where: the folder they're in on this computer (see ascii_name).
    Names that differ only in case count as the same: the SD card's file
    system (exFAT or FAT32) ignores case.
    """
    folders = folders or set()
    taken: set[str] = set()
    result: dict[str, str] = {}
    for name in sorted(names, key=str.lower):
        is_folder = name in folders
        candidate = (folder_name(name, where) if is_folder else ascii_name(name, where)) if plain else name
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
