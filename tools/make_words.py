"""Makes kaidrop/data/words-zh.xz, the Chinese words chinese.py splits names
into, from the dictionary that comes with jieba 0.42.1 (MIT licence):

    pip install jieba==0.42.1
    python tools/make_words.py

Each line of the output is "word<SPACE>frequency", as jieba reads them. Kept:
every single hanzi, and the words seen at least MIN_FREQUENCY times. The rest
(about 210,000 rare words and set phrases) would make the .exe bigger and
join too much: with them 我爱你 is one word (Woaini) and 月亮代表 another;
without them they're Wo Ai Ni and Yueliang Daibiao, as pinyin writes words.
"""
from __future__ import annotations

import lzma
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "kaidrop" / "data" / "words-zh.xz"
MIN_FREQUENCY = 5


def main() -> None:
    import jieba  # Only to find its dictionary.

    source = Path(jieba.__file__).resolve().parent / "dict.txt"
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        word, frequency = line.split(" ")[:2]
        if len(word) == 1 or int(frequency) >= MIN_FREQUENCY:
            lines.append(f"{word} {frequency}\n")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(lzma.compress("".join(lines).encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))
    print(f"{len(lines)} words, {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
