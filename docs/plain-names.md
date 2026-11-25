# Plain names for Switch 2

[Back to the README](../README.md)

## The problem

On Switch 2, a file or folder whose name has a character outside basic
ASCII is saved to the SD card, but the console's file system leaves it out of
its folder:

- That means an accented letter such as **á, é, ñ, ü**, typographic quotes
  such as **’**, or Japanese, Chinese or Korean.
- The file isn't listed, and it isn't even counted among the folder's
  entries.
- Every app sees folders through that file system, so every app is affected:
  FTP listings, OunceShell's file browser, KaiPlayer and any other homebrew.
- The file takes up space but nothing can see it, and nothing on the console
  can find it to rename it: the names have to be right before the files get
  there.

So `06 Canción.flac` uploaded with FileZilla is invisible, while
`06 Cancion.flac` works.

## What KaiDrop does

With **Plain names for Switch 2** on (the default), KaiDrop gives each copy
on the console a name it can list:

- accents are dropped: `Canción` → `Cancion`, `Ñandú` → `Nandu`;
- typographic punctuation becomes plain: `Why’d` → `Why'd`, `–` → `-`;
- other alphabets are written in Latin letters, by language (see
  [below](#other-alphabets)): `水色.mp3` → `Mizuiro.mp3`,
  `한국어.mp3` → `Hangugeo.mp3`, `Москва.mp3` → `Moskva.mp3`;
- anything left, like emoji, becomes `_`;
- names that would clash get a number: `Cancion (2).mp3`;
- a name longer than 240 characters is cut (the card takes 255).

**Your files on the computer are never renamed or changed.** Only the copies
on the console get the new names.

## Other alphabets

| Written in | As | Example |
|------------|----|---------|
| Japanese | romaji (Hepburn) | `04 水色の空.mp3` → `04 Mizuiro no Sora.mp3` |
| Chinese | pinyin, without tones | `我爱北京.mp3` → `Wo Ai Beijing.mp3` |
| Korean | Revised Romanization | `한국 노래.mp3` → `Hanguk Norae.mp3` |
| Cyrillic, Greek | their usual Latin spelling | `Москва` → `Moskva`, `Ελληνικά` → `Ellinika` |
| Arabic, Hebrew, Thai, Hindi and the rest | letter by letter | `שלום` → `slvm` |

**Japanese.** Kanji have several readings (水色 is *mizuiro*, not
*suishoku*), so KaiDrop splits the name into words and reads each one with a
list of half a million Japanese words and their readings, made from
[UniDic](https://clrd.ninjal.ac.jp/unidic/). Words start with a capital;
particles are in lower case, as said (`は` → `wa`, `を` → `o`); endings
join their word (`書いた` → `Kaita`, `待って` → `Matte`). Long vowels are
short, as plain Hepburn writes them without macrons: `東京` → `Tokyo`,
`大阪` → `Osaka`, `コーヒー` → `Kohi`; `ei` stays (`先生` → `Sensei`), and so
does a vowel that's said twice (`思う` → `Omou`). It's right for most names,
but it doesn't understand the sentence, so now and then a word gets another
of its readings.

**Chinese.** Pinyin with [pypinyin](https://github.com/mozillazg/python-pinyin),
without tone marks (`ü` is `u`), a word at a time, as pinyin is written: the
name is split into words with [jieba](https://github.com/fxsjy/jieba), so
`北京欢迎你` → `Beijing Huanying Ni`, `月亮代表我的心` → `Yueliang Daibiao Wo
De Xin`, `汉字` → `Hanzi`, `重庆` → `Chongqing`.

**Korean.** Each syllable's letters, with the Revised Romanization's rules
for the letters that meet between syllables (`국물` → `Gungmul`, `신라` →
`Silla`).

**The rest** with [anyascii](https://github.com/anyascii/anyascii). Arabic and
Hebrew are written without their vowels, as they are in their own script.

### Japanese or Chinese?

Kanji alone can be either. KaiDrop decides for each name:

1. **Kana in the name, or in a folder above it** (ひらがな, カタカナ): Japanese,
   since Chinese doesn't use kana. `雨.mp3` in a folder `みずいろ楽団` is
   `Ame.mp3`.
2. **Otherwise, a character only Chinese writes**, in the name or a folder
   above it (simplified ones such as `门`, `爱`, `东`, where Japanese has
   `門`, `愛`, `東`): Chinese. `雨.mp3` in a folder `中国音乐` is `Yu.mp3`.
3. **Otherwise Japanese**: `水色.mp3` is `Mizuiro.mp3`. Traditional Chinese
   with no simplified character, such as Taiwan's or Hong Kong's, is read as
   Japanese too.

That's **Kanji: Automatic**, the default. The list next to **Plain names for
Switch 2** changes it, and KaiDrop remembers the choice:

| Kanji | Reads kanji as | `北京.mp3` | `水色.mp3` in a folder `みずいろ` | `水色の雨.mp3` |
|-------|----------------|------------|-----------------------------------|----------------|
| Automatic | the rules above | `Pekin.mp3` | `Mizuiro.mp3` | `Mizuiro no Ame.mp3` |
| Japanese | Japanese, always | `Pekin.mp3` | `Mizuiro.mp3` | `Mizuiro no Ame.mp3` |
| Chinese | Chinese, unless the name itself has kana | `Beijing.mp3` | `Shuise.mp3` | `Mizuiro no Ame.mp3` |

Choose **Chinese** for a Chinese collection without simplified characters
(Taiwan's, Hong Kong's), and **Japanese** for a Japanese one where a folder
name happens to look Chinese. A name with kana is always Japanese.

Before sending, KaiDrop shows each file's name on your computer and on the
console (renamed ones in color). With plain names on, folders made or renamed
on the console get plain names too.

## Playlists keep working

A playlist (`.m3u`, `.m3u8` or `.pls`) lists its songs by path, so once the
songs or their folders get plain names, the old paths lead nowhere. When
KaiDrop sends a playlist, the copy on the console points to the names the
songs have there:

- an entry relative to the playlist (`../Artista Ñ/06 Canción.flac`, as in
  most playlists) gets the same plain names as the song and the folders on
  its way: `../Artista N/06 Cancion.flac`;
- an absolute entry (`C:\Music\Artista Ñ\06 Canción.flac` or `file:///…`)
  whose song is being sent too becomes relative to the playlist on the
  console; one outside what's sent is left as it was, and the Log tab says
  how many there are;
- a song sent in the same batch gets its new name; for one sent before,
  KaiDrop checks it's on the console. An entry whose song isn't on the
  console, or not on this computer, is left as it was;
- `#EXTM3U`, `#EXTINF` and other comment lines, the line endings and the
  encoding stay as they were (`.m3u8` is UTF-8; `.m3u` and `.pls` the
  Windows code page, or UTF-8). New paths use `/`;
- an `.m3u` or `.m3u8` whose own name gets a plain one keeps its name
  inside, in a `#PLAYLIST:` line after `#EXTM3U` (UTF-8, up to 48
  characters): `北京欢迎你.m3u8` goes as `Beijing Huanying Ni.m3u8`, and
  KaiPlayer still calls it `北京欢迎你`. A `#PLAYLIST:` line it already has
  is kept;
- a playlist over 4 MB is sent as it is.

This works with the songs and playlists laid out on the console as on the
computer (a playlist in `Music\Playlists` with songs in `Music\Artist`).
[KaiPlayer](https://github.com/mizuiroame/kaiplayer) reads playlists from
the `Playlists` folder of its music folder, with paths relative to it.

**The playlist on the computer isn't changed**, only its copy on the console.
Receiving a playlist back brings the console's copy as it is, with the plain
names.

## Song titles keep their accents

Music players such as [KaiPlayer](https://github.com/mizuiroame/kaiplayer)
read the title, artist and album from the songs' tags, so they still show
**Canción** with its accent, or the Japanese title, whatever the file is
called. That relies on the songs being tagged: a song without tags is shown
by its file name, which on the console is the plain one.
