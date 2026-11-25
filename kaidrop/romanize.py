"""Names in other alphabets written in Latin letters, by language.

- Japanese in romaji (水色 -> Mizuiro), see japanese.py.
- Chinese in pinyin without tones (北京 -> Beijing), with pypinyin.
- Korean in the Revised Romanization (한국어 -> Hangugeo), see hangul.py.
- Cyrillic, Greek, Arabic, Hebrew, Thai and the other scripts with anyascii
  (Москва -> Moskva).

Kanji alone could be Japanese or Chinese. The name, then each folder above
it from the nearest one up, is looked at until one tells:
- kana (ひらがな or カタカナ) say Japanese: Chinese never uses them;
- a character Japanese doesn't write, as Chinese simplified ones (门, 爱,
  东; Japanese has 門, 愛, 東), says Chinese.
If none tells, kanji are Japanese.
So 水色の雨.mp3 and 水色.mp3 are Japanese (Mizuiro), and so is 雨.mp3 in a
folder called みずいろ; 我爱你.mp3, or 北京.mp3 in a folder called 中国音乐, is
Chinese, even inside a folder called 音楽ライブラリ (the nearer one tells
first). Traditional Chinese with no simplified letter (周杰倫) is read as
Japanese.

That's AUTO, the default. The "Kanji" setting can change it:
- JAPANESE: kanji are always Japanese;
- CHINESE: kanji are Chinese, unless the name itself has kana (then it's
  Japanese for sure).
"""
from __future__ import annotations

import re
import unicodedata

from . import hangul, japanese
from .kana import is_kana

# How kanji are read (the "Kanji" setting).
AUTO, JAPANESE, CHINESE = "auto", "japanese", "chinese"
KANJI_MODES = (AUTO, JAPANESE, CHINESE)

# Punctuation used with Chinese and Japanese, with a plain look-alike.
_CJK_PUNCTUATION = str.maketrans({
    "・": " ", "、": ", ", "。": ". ", "〜": "-", "「": "'", "」": "'", "『": "'", "』": "'",
    "【": "[", "】": "]", "〔": "[", "〕": "]", "《": "'", "》": "'", "〈": "'", "〉": "'",
})


def _chinese(text: str) -> str:
    """Hanzi in pinyin without tones, a word at a time: 北京天安门 -> Beijing Tian An Men."""
    try:  # Loads its dictionary: only when needed.
        from pypinyin import Style, lazy_pinyin
        from pypinyin.seg.mmseg import seg
    except ImportError:  # Run from source without it: the hanzi become "_".
        return text

    words = []
    for word in seg.cut(text):
        latin = "".join(lazy_pinyin(word, style=Style.NORMAL, v_to_u=True, errors=lambda _: ""))
        if latin:
            words.append(latin[:1].upper() + latin[1:])
    return " ".join(words)


def _other(c: str) -> str:
    """Any other letter or digit (Cyrillic, Greek, Arabic, Thai...) in Latin letters."""
    if c.isascii() or unicodedata.category(c)[0] not in "LN":
        return c
    try:
        from anyascii import anyascii
    except ImportError:  # Run from source without it: the letter becomes "_".
        return c
    return anyascii(c)


def _script(c: str, kanji_japanese: bool) -> str:
    if hangul.is_hangul(c):
        return "ko"
    if is_kana(c) or (japanese.is_kanji(c) and kanji_japanese):
        return "ja"
    if japanese.is_kanji(c):
        return "zh"
    return ""


def preload() -> None:
    """Loads the dictionaries ahead of time, so the first names don't wait."""
    japanese.preload()
    _chinese("中")
    _other("Я")


def has_kana(text: str) -> bool:
    return any(is_kana(c) for c in text)


def kanji_are_japanese(name: str, where: str = "", kanji: str = AUTO) -> bool:
    """How the kanji in a name are read (see the rules above)."""
    if kanji == JAPANESE or has_kana(name):
        return True
    if kanji == CHINESE:
        return False
    for part in [name, *reversed(re.split(r"[\\/]", where))]:  # The nearest folder first.
        if has_kana(part):
            return True
        if any(japanese.is_kanji(c) and not japanese.uses(c) for c in part):
            return False
    return True


def romanize(name: str, where: str = "", kanji: str = AUTO) -> str:
    """name with its letters in Latin letters (accents are left for names.py).
    where: the folder it's in, which tells Japanese kanji from Chinese;
    kanji: AUTO, JAPANESE or CHINESE (see above)."""
    if name.isascii():
        return name
    text = unicodedata.normalize("NFKC", name).translate(_CJK_PUNCTUATION)
    kanji_japanese = kanji_are_japanese(text, unicodedata.normalize("NFKC", where), kanji)
    out: list[str] = []
    i = 0
    while i < len(text):
        script = _script(text[i], kanji_japanese)
        if not script:
            out.append(_other(text[i]))
            i += 1
            continue
        j = i
        while j < len(text) and (_script(text[j], kanji_japanese) == script or (script == "ja" and text[j] == "ー")):
            j += 1
        run = text[i:j]
        if script == "ja":
            latin = japanese.romanize(run, _chinese)
        elif script == "zh":
            latin = _chinese(run)
        else:
            latin = hangul.romanize(run)
            latin = latin[:1].upper() + latin[1:]
        # A space between the words and letters or digits next to them.
        if out and out[-1] and (out[-1][-1].isalnum() or out[-1][-1] in ")]"):
            latin = " " + latin
        if j < len(text) and (text[j].isalnum() or text[j] in "([") and _script(text[j], kanji_japanese) != script:
            latin += " "
        out.append(latin)
        i = j
    return re.sub(r" {2,}", " ", "".join(out)).replace(" ,", ",")
