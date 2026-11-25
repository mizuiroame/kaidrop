"""Makes kaidrop/data/readings-ja.xz, the Japanese readings romaji.py uses,
from UniDic's lexicon (UniDic 2.1.2 for MeCab, BSD licence option).

Get unidic-mecab-2.1.2_src.zip from
https://clrd.ninjal.ac.jp/unidic_archive/cwj/2.1.2/ and pass its lex.csv:

    python tools/make_readings.py path/to/lex.csv

Each line of the output is "surface<TAB>reading<TAB>cost<TAB>kind", one per
written form and kind (the most common reading, the one with the lowest cost):
- reading: in katakana, left empty when it's the surface itself in katakana;
- cost: UniDic's word cost (lower is more common);
- kind: P a particle (a word of its own, in lower case), A an ending that
  joins the word before it (書い+た -> kaita), I a verb or adjective in one
  of its forms (書い), W any other word.
Words written only in katakana are left out: they're read letter by letter.
"""
from __future__ import annotations

import csv
import lzma
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "kaidrop" / "data" / "readings-ja.xz"
MAX_LENGTH = 12  # Longer written forms are rare in names and take room.
_SKIP_POS = {"記号", "補助記号", "空白"}


def _is_japanese(c: str) -> bool:
    o = ord(c)
    return (0x3041 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
            or 0xF900 <= o <= 0xFAFF or o in (0x3005, 0x3006))


def _katakana(text: str) -> str:
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in text)


def _kind(pos1: str, pos2: str, ctype: str) -> str:
    if pos1 == "助詞":
        return "A" if pos2 == "接続助詞" else "P"
    if pos1 in ("助動詞", "接尾辞"):
        return "A"
    return "I" if ctype != "*" else "W"


def main(lex: Path) -> None:
    best: dict[tuple[str, str], tuple[int, str]] = {}
    with open(lex, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            surface, cost, pos1, pos2 = row[0], int(row[3]), row[4], row[5]
            ctype, lform, pron = row[8], row[10], row[13]
            if (pos1 in _SKIP_POS or len(surface) > MAX_LENGTH or not all(map(_is_japanese, surface))
                    or all(0x30A1 <= ord(c) <= 0x30FF for c in surface)):
                continue
            # Words that don't change keep their spelling (センセイ, not センセー);
            # particles and inflected forms are read as said (は is ワ).
            reading = pron if pos1 == "助詞" or ctype != "*" else lform
            if not reading or reading == "*":
                continue
            key = (surface, _kind(pos1, pos2, ctype))
            if key not in best or cost < best[key][0]:
                best[key] = (cost, reading)
    lines = []
    for surface, kind in sorted(best):
        cost, reading = best[surface, kind]
        shown = "" if reading == _katakana(surface) else reading
        lines.append(f"{surface}\t{shown}\t{cost}\t{kind}\n")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(lzma.compress("".join(lines).encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))
    print(f"{len(lines)} words, {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
