"""Japanese in Latin letters (romaji): 水色の雨 -> Mizuiro no Ame.

Kanji have several readings (水色 is "mizuiro", not "suishoku"), so the
words are looked up in a list of readings made from UniDic's lexicon
(data/readings-ja.xz, see tools/make_readings.py). A name is split into the
words that make the most likely sentence (UniDic gives each word a cost:
the lower, the more common; a few rules say what can follow what: an ending
follows a word, best a verb's form), then each word is written in Hepburn:
- a particle (の, は, を...) in lower case, as said (は -> wa);
- an ending (書い+た, 待っ+て) joined to the word before it;
- other words with a capital letter.
A katakana run is one word, letter by letter. A kanji that isn't in the
list as a word of its own gets its Chinese reading.
"""
from __future__ import annotations

import lzma
import threading
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .kana import is_kana, romanize as kana_romaji, to_katakana

DATA = Path(__file__).resolve().parent / "data" / "readings-ja.xz"
_MAX_WORD = 12
_UNKNOWN_KANA = 12000      # A kana that starts no word in the list.
_UNKNOWN_KANJI = 20000     # A kanji with no reading in the list.
_KATAKANA_RUN = 3000       # A katakana word, whatever its length.
_INFINITE = 1 << 60
# What a word's kind costs after the kind before it ("" is the start).
_AFTER = {("", "A"): 4000, ("", "P"): 1500, ("P", "A"): 3000, ("W", "A"): 1500, ("I", "A"): -2000}
_lock = threading.Lock()
_words: _Readings | None = None


@dataclass(frozen=True)
class Word:
    text: str       # As written.
    latin: str      # In Latin letters, lower case ("" for a kanji not in the list).
    kind: str       # W a word, I a verb's form, P a particle, A an ending, ? not in the list.


def is_kanji(c: str) -> bool:
    o = ord(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF or o in (0x3005, 0x3006)


class _Readings:
    """The list of readings, kept as its text (sorted by word) with where
    each line starts: half a million words in about 20 MB, not 150 as a dict."""

    def __init__(self, text: str) -> None:
        self.text = text
        starts = array("I", [0])
        at = text.find("\n")
        while at != -1:
            starts.append(at + 1)
            at = text.find("\n", at + 1)
        if starts[-1] >= len(text):
            starts.pop()
        self.starts = starts
        self.kanji = frozenset(c for c in set(text) if is_kanji(c))

    def _surface(self, k: int) -> str:
        start = self.starts[k]
        return self.text[start:self.text.find("\t", start)]

    def get(self, surface: str) -> list[tuple[str, int, str]]:
        """Each (reading in katakana, cost, kind) the word has."""
        lo, hi = 0, len(self.starts)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._surface(mid) < surface:
                lo = mid + 1
            else:
                hi = mid
        found = []
        while lo < len(self.starts) and self._surface(lo) == surface:
            start = self.starts[lo]
            end = self.text.find("\n", start)
            _, reading, cost, kind = self.text[start:end if end != -1 else None].split("\t")
            found.append((reading or to_katakana(surface), int(cost), kind))
            lo += 1
        return found


def _load() -> _Readings:
    """The readings, loaded the first time a Japanese name needs them."""
    global _words
    with _lock:
        if _words is None:
            try:
                text = lzma.decompress(DATA.read_bytes()).decode("utf-8")
            except (OSError, lzma.LZMAError, UnicodeDecodeError):
                text = ""  # Without the list, kana still work and kanji get Chinese readings.
            _words = _Readings(text)
        return _words


def uses(c: str) -> bool:
    """True if Japanese writes this kanji: Chinese simplified forms such as
    门 or 爱 (Japanese 門, 愛) are in no Japanese word."""
    return c in _load().kanji


def preload() -> None:
    """Loads the readings ahead of time (they take a moment)."""
    _load()


def _is_katakana(c: str) -> bool:
    return 0x30A1 <= ord(c) <= 0x30FA


def _options(text: str, i: int, words: _Readings) -> list[tuple[int, int, Word]]:
    """The words that can start at text[i]: (where it ends, its cost, the word)."""
    n = len(text)
    options = []
    for j in range(i + 1, min(n, i + _MAX_WORD) + 1):
        for reading, cost, kind in words.get(text[i:j]):
            options.append((j, cost, Word(text[i:j], kana_romaji(reading), kind)))
    if _is_katakana(text[i]):
        j = i + 1
        while j < n and (_is_katakana(text[j]) or text[j] == "ー"):
            j += 1
        options.append((j, _KATAKANA_RUN, Word(text[i:j], kana_romaji(text[i:j]), "W")))
    if not options:
        c = text[i]
        if is_kana(c):
            options.append((i + 1, _UNKNOWN_KANA, Word(c, kana_romaji(c), "?")))
        else:
            options.append((i + 1, _UNKNOWN_KANJI, Word(c, "", "?")))
    return options


def split(text: str) -> list[Word]:
    """The words in a run of Japanese (kanji and kana), the likeliest way."""
    words = _load()
    n = len(text)
    # best[i][kind]: the cheapest way to reach i with a word of that kind last.
    best: list[dict[str, tuple[int, int, str, Word | None]]] = [{} for _ in range(n + 1)]
    best[0][""] = (0, -1, "", None)
    for i in range(n):
        if not best[i]:
            continue
        for j, cost, word in _options(text, i, words):
            for before, (total, _, _, _) in best[i].items():
                total += cost + _AFTER.get((before, word.kind), 0)
                if word.kind not in best[j] or total < best[j][word.kind][0]:
                    best[j][word.kind] = (total, i, before, word)
    out: list[Word] = []
    kind = min(best[n], key=lambda k: best[n][k][0])
    j = n
    while j > 0:
        _, i, before, word = best[j][kind]
        out.append(word)
        j, kind = i, before
    return out[::-1]


def romanize(text: str, chinese: Callable[[str], str] | None = None) -> str:
    """A run of Japanese in Latin letters. chinese(kanji) reads a kanji the
    list doesn't have (it gets its Chinese reading)."""
    parts: list[str] = []
    takes_ending = False  # The last part is a word an ending can join.
    for word in split(text):
        latin = word.latin
        if not latin and chinese:
            latin = chinese(word.text).lower()
        if not latin:
            continue
        if parts and takes_ending and (word.kind == "A" or (word.kind == "?" and is_kana(word.text))):
            parts[-1] += latin  # Kana the list doesn't know stay with the word before.
            continue
        if word.kind == "P":
            parts.append(latin)
            takes_ending = False
        else:
            parts.append(latin[:1].upper() + latin[1:])
            takes_ending = True
    return " ".join(parts)
