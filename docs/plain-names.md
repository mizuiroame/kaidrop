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
- other characters, like Japanese, become `_`: `04 みずいろの雨.mp3` →
  `04 _.mp3`;
- names that would clash get a number: `Cancion (2).mp3`.

**Your files on the computer are never renamed or changed.** Only the copies
on the console get the new names.

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
