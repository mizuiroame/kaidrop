"""Korean in Latin letters, in the Revised Romanization of Korean (2000).

Each syllable block is split into its letters; a final consonant is written
by what follows it, as the romanization's rules say: carried over before a
vowel (한국어 -> hangugeo), nasal before ㄴ and ㅁ (국물 -> gungmul), and
ㄴ next to ㄹ as "ll" (신라 -> silla). Rules that depend on the word's
meaning (as with 묵호, where ㅎ isn't aspirated) aren't applied.
"""
from __future__ import annotations

_FIRST = 0xAC00
_LAST = 0xD7A3

_INITIALS = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_VOWELS = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
           "yu", "eu", "ui", "i")
# The finals at the end of a word or before a consonant, and before a vowel
# (when the next syllable starts with the silent ㅇ).
_FINALS = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
           "ng", "t", "t", "k", "t", "p", "t")
_FINALS_LINKED = ("", "g", "kk", "ks", "n", "nj", "n", "d", "r", "lg", "lm", "lb", "ls", "lt", "lp", "r", "m", "b",
                  "ps", "s", "ss", "ng", "j", "ch", "k", "t", "p", "")
_SILENT = 11  # ㅇ as an initial.
_N, _R, _M, _H = 2, 5, 6, 18  # Initials ㄴ, ㄹ, ㅁ, ㅎ.
_FINAL_N, _FINAL_L, _FINAL_H = 4, 8, 27
_ASPIRATED = {0: "k", 3: "t", 12: "ch"}  # ㄱ, ㄷ, ㅈ after ㅎ.


def is_hangul(c: str) -> bool:
    return _FIRST <= ord(c) <= _LAST


def _split(c: str) -> tuple[int, int, int]:
    code = ord(c) - _FIRST
    return code // 588, (code % 588) // 28, code % 28


def _join(final: int, initial: int) -> tuple[str, str]:
    """How a final consonant and the next syllable's initial are written."""
    coda = _FINALS[final]
    onset = _INITIALS[initial]
    if initial == _SILENT:
        return _FINALS_LINKED[final], ""
    if final == _FINAL_H and initial in _ASPIRATED:
        return "", _ASPIRATED[initial]
    if initial in (_N, _M):
        if final == _FINAL_L or coda == "l":
            return "l", "l" if initial == _N else onset
        coda = {"k": "ng", "t": "n", "p": "m"}.get(coda, coda)
    elif initial == _R:
        if coda in ("l", "n"):
            return "l", "l"
        if coda:
            return {"k": "ng", "t": "n", "p": "m"}.get(coda, coda), "n"
    return coda, onset


def romanize(text: str) -> str:
    """A run of Hangul syllables in Latin letters, in lower case."""
    blocks = [_split(c) for c in text]
    out = []
    for i, (initial, vowel, final) in enumerate(blocks):
        if i == 0:
            out.append(_INITIALS[initial])
        out.append(_VOWELS[vowel])
        if i + 1 < len(blocks):
            coda, onset = _join(final, blocks[i + 1][0])
            out.append(coda + onset)
        else:
            out.append(_FINALS[final])
    return "".join(out)
