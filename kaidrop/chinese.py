"""Chinese in pinyin without tones, a word at a time: 北京欢迎你 -> Beijing
Huanying Ni, 汉字 -> Hanzi.

Names are split into words by jieba, with a smaller copy of its dictionary
(data/words-zh.xz, see tools/make_words.py); hanzi it doesn't know are
joined by jieba's own guess (its HMM). Each word is then read by pypinyin.
Both load the first time a Chinese name needs them, not before.
"""
from __future__ import annotations

import io
import logging
import lzma
import threading
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "words-zh.xz"

_lock = threading.Lock()
_tokenizer = None   # jieba's, once loaded.
_loaded = False


def _load_tokenizer():
    """jieba with KaiDrop's word list, or None without either."""
    try:
        import jieba
    except ImportError:
        return None
    try:
        data = lzma.decompress(DATA.read_bytes())
    except (OSError, lzma.LZMAError):
        return None
    jieba.setLogLevel(logging.WARNING)
    tokenizer = jieba.Tokenizer()
    # The list is read here, not with tokenizer.initialize(): that one also
    # writes a cache file to %TEMP%, a new one each time the .exe runs.
    tokenizer.FREQ, tokenizer.total = tokenizer.gen_pfdict(io.BytesIO(data))
    tokenizer.initialized = True
    return tokenizer


def _tokenizer_or_none():
    global _tokenizer, _loaded
    with _lock:
        if not _loaded:
            _tokenizer = _load_tokenizer()
            _loaded = True
        return _tokenizer


def words(text: str) -> list[str]:
    """text (hanzi only) split into words."""
    tokenizer = _tokenizer_or_none() if len(text) > 1 else None
    if tokenizer is not None:
        return list(tokenizer.cut(text, HMM=True))
    if len(text) > 1:  # Run from source without jieba: pypinyin's own split.
        try:
            from pypinyin.seg.mmseg import seg
            return list(seg.cut(text))
        except ImportError:
            pass
    return [text]


def romanize(text: str) -> str:
    """Hanzi in pinyin without tones, each word capitalized and on its own."""
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:  # Run from source without it: the hanzi become "_".
        return text
    latin = []
    for word in words(text):
        syllables = "".join(lazy_pinyin(word, style=Style.NORMAL, v_to_u=True, errors=lambda _: ""))
        if syllables:
            latin.append(syllables[:1].upper() + syllables[1:])
    return " ".join(latin)


def preload() -> None:
    """Loads pypinyin ahead of time (jieba waits for a Chinese name)."""
    romanize("中")
