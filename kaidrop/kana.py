"""Kana in Latin letters (Hepburn): しゃしん -> shashin, コーヒー -> kohi.

Long vowels are short, as plain Hepburn writes them without macrons: the
long-vowel mark ー is left out. Kana spelled out (トウキョウ) are written as
they are; japanese.py's readings already leave out the ones that only
lengthen a vowel (東京 is read トキョ, Tokyo).
"""
from __future__ import annotations

_BASE = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヰ": "i", "ヱ": "e", "ヲ": "o", "ン": "n",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "ヴ": "vu", "ヵ": "ka", "ヶ": "ke", "ヷ": "va", "ヺ": "vo",
}
_SMALL_VOWELS = {"ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o", "ヮ": "wa"}
_SMALL_Y = {"ャ": "a", "ュ": "u", "ョ": "o"}
_SOKUON = "ッ"
_LONG = "ー"
_REPEAT = {"ヽ": False, "ヾ": True}  # Repeat the kana before (True: voiced).
_VOICED = {k: v for k, v in zip("カキクケコサシスセソタチツテトハヒフヘホウ", "ガギグゲゴザジズゼゾダヂヅデドバビブベボヴ")}


def to_katakana(text: str) -> str:
    """Hiragana (and its repeat marks ゝゞ) as katakana."""
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x309E else c for c in text)


def is_kana(c: str) -> bool:
    return 0x3041 <= ord(c) <= 0x30FF and c not in "・゠"


def _small(prev: str, small: str) -> str:
    """A syllable with a small kana: キャ, シェ, ファ, ティ, ウィ..."""
    if small in _SMALL_Y:
        if prev.endswith(("sh", "ch", "j")) or prev[:-1].endswith(("sh", "ch", "j")):
            return prev[:-1] + _SMALL_Y[small]
        return prev[:-1] + "y" + _SMALL_Y[small]
    vowel = _SMALL_VOWELS[small]
    if prev == "u":
        return "w" + vowel
    if prev == "i":
        return "y" + vowel
    if prev == "tsu":
        return "ts" + vowel
    return prev[:-1] + vowel


def romanize(text: str) -> str:
    """Kana in lower-case Latin letters; anything else is left as it is."""
    syllables: list[str] = []
    double = False
    for c in to_katakana(text):
        if c in _REPEAT and syllables:
            kana = syllables[-1]
            c = _VOICED.get(kana[0], kana[0]) if _REPEAT[c] else kana[0]
        if c == _SOKUON:
            double = True
            continue
        if c == _LONG:
            continue  # Long vowels are written short.
        if (c in _SMALL_Y or c in _SMALL_VOWELS) and syllables and syllables[-1][0] in _BASE:
            kana, prev = syllables.pop()
            syllables.append((kana, _small(prev, c)))
            continue
        latin = _BASE.get(c) or _SMALL_VOWELS.get(c) or {"ャ": "ya", "ュ": "yu", "ョ": "yo"}.get(c) or c
        if double and latin[0] in "bcdfghjkmprstvwz":
            latin = ("t" if latin.startswith("ch") else latin[0]) + latin
        double = False
        syllables.append((c, latin))
    out = []
    for i, (kana, latin) in enumerate(syllables):
        # ン before a vowel or y: "n'" (kan'i, not kani).
        if kana == "ン" and i + 1 < len(syllables) and syllables[i + 1][1][:1] in tuple("aiueoy"):
            latin = "n'"
        out.append(latin)
    if double:
        out.append("t")  # A final ッ, as in 待っ+て -> mat+te.
    return "".join(out)
