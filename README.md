# KaiDrop

**Send music (or anything) from your computer to a Switch 2 running kaiHEN,
over FTP — with file names the console can actually list.**

> **Work in progress.** Sending and receiving work (tested with over a
> gigabyte of music on a Switch 2).

![KaiDrop](docs/kaidrop.png)

## The problem

On Switch 2, a file or folder whose name has a character outside basic
ASCII — an accented letter such as **á, é, ñ, ü**, typographic quotes such as
**’**, or Japanese, Chinese or Korean — is saved to the SD card, but the
console's file system leaves it out of its folder: it isn't listed, and it
isn't even counted among the folder's entries. Every app sees folders through
that file system, so every app is affected: FTP listings, OunceShell's file
browser, KaiPlayer and any other homebrew. The file takes up space but
nothing can see it, and nothing on the console can find it to rename it: the
names have to be right before the files get there.

So `06 Canción.flac` uploaded with FileZilla is invisible, while
`06 Cancion.flac` works.

## What KaiDrop does

- Sends folders and files over FTP, keeping the folder structure, and
  receives them back from the console the same way. It works with any FTP
  server; on the console, use OunceShell's.
- With **Plain names for Switch 2** on (the default), it gives each copy on
  the console a name it can list:
  - accents are dropped: `Canción` → `Cancion`, `Ñandú` → `Nandu`;
  - typographic punctuation becomes plain: `Why’d` → `Why'd`, `–` → `-`;
  - other characters, like Japanese, become `_`: `04 みずいろの雨.mp3` →
    `04 _.mp3`;
  - names that would clash get a number: `Cancion (2).mp3`.
- **Your files on the computer are never renamed or changed.** Only the
  copies on the console get the new names.
- Shows, before sending, each file's name on your computer and on the
  console (renamed ones in color).
- When a file is already on the console, asks what to do, showing both
  files' names, sizes and dates: **Skip**, **Replace**, **Keep both** (the
  new one is sent as `name (2)`) or **Cancel the batch** — for that file or
  for every one in the batch. Sending a folder again after adding songs:
  choose Skip for all.

  ![When a file is already there](docs/conflict.png)

- Shows whether it's connected, notices when the server goes away (OunceShell
  closed, the console asleep) and offers **Reconnect**, then continues with
  the files left. A file only gets its name on arrival once it's complete,
  so a lost connection never leaves a half song that looks whole. While
  moving files it shows the speed and the time left. The **Log** tab lists
  what happened, with the time, like FileZilla's message log.
- Remembers the console's address and the destination folder.

Music players such as [KaiPlayer](https://github.com/mizuiroame/kaiplayer)
read the title, artist and album from the songs' tags, so they still show
**Canción** with its accent, or the Japanese title, whatever the file is
called. That relies on the songs being tagged: a song without tags is shown
by its file name, which on the console is the plain one.

## Use it

1. On the console, open **OunceShell** and start its **FTP server**. Note
   the IP address and port it shows.
2. On your computer, open **KaiDrop**, type the **Host** (the IP address)
   and **Port** (and the user and password, if your server asks for them),
   and press **Connect**.
3. KaiDrop looks like FileZilla: **your computer on the left, the console on
   the right**. On the left, a folder tree like Explorer's starts from
   Desktop, Documents, Downloads, Music and your drives (by name, such as
   *Data (D:)*); the folder's contents are below it. Browse both sides
   (double-click a folder, **↑** goes up, or type a path and press Enter).
   **Right-click** for more: on the left, *Send to the server*, *Open*,
   *New folder* and *Refresh*; on the right, *Open*, *New folder*, *Rename*
   (F2), *Delete* (Del) and *Refresh* (F5). With plain names on, folders
   made or renamed on the console get plain names too.
4. **Send** files or folders by **dragging them from the left onto the
   right** (onto a folder to send them into it), by dragging them from
   Explorer, or with **right-click → Send to the server**. **Receive** them the
   other way: drag from the right onto the left, or **right-click → Download to
   this computer** (into the folder shown on the left). While you drag, a label
   by the pointer shows what you're moving and where it will land, and the
   folder under the pointer lights up. Select several as in Explorer:
   **Ctrl+click** adds or removes one, **Shift+click** selects a range,
   **Shift+↑/↓** (and Shift+Home/End) extend the selection from the keyboard,
   and **Ctrl+A** selects everything. Dragging any of the selected files takes
   them all.
5. The **Transfers** tab shows each file, where it comes from and goes
   (renamed ones in color) and how it went; above it, how much is done, the
   speed and the time left (*11.7 MB of 1.1 GB · 3.9 MB/s · 4 min 50 s
   left*). **Cancel** stops the batch being
   moved (a half-moved file is removed); **Clear finished** tidies the list.
   A file being moved is called `name.part` until it's complete, so if the
   connection is lost halfway, no half file is left with the real name (a
   leftover `.part` can be deleted, and sending again replaces it).
   A file already where another is going (on the console when sending, on
   your computer when receiving) asks first: skip, replace, keep both or
   cancel.
   The **Log** tab shows what KaiDrop did and what the server said.
6. Next to **Connect**, a dot shows the connection. If it turns red
   (*Connection lost*), start OunceShell's FTP server again and press
   **Reconnect**. Files that were still to be moved show as *Stopped*;
   after reconnecting, KaiDrop offers to continue with them (the ones
   already moved aren't sent again).

## Download

Get `KaiDrop.exe` (Windows) from
[Releases](https://github.com/mizuiroame/kaidrop/releases). It needs nothing
else installed.

On macOS or Linux, run it from source with Python 3.10 or later (Tkinter
included):

```
python -m kaidrop
```

## For developers

```
python -m unittest discover -s tests -t .          # tests (FTP tests need pyftpdlib)
pip install -r requirements-dev.txt                # pyftpdlib and PyInstaller
powershell -File build.ps1                         # builds dist/KaiDrop.exe
```

| File | What it does |
|------|--------------|
| `kaidrop/names.py` | The plain names for the console |
| `kaidrop/plan.py` | What to send where: the files and their names on the console |
| `kaidrop/ftp.py` | Sending: folders, files already there, `.part` until complete, cancel |
| `kaidrop/download.py` | Receiving: what comes where, names Windows allows, `.part` until complete |
| `kaidrop/batch.py` | A batch in the queue, and what's left of it to continue after Reconnect |
| `kaidrop/rate.py` | The speed and time left |
| `kaidrop/app.py` | The window: connection, the two panes, transfers, log |
| `kaidrop/panes.py` | The file panes: this computer and the server, right-click menus, selection |
| `kaidrop/foldertree.py` | This computer's folder tree, like Explorer's |
| `kaidrop/places.py` | Where the tree starts: Desktop, Documents… and the drives, by name |
| `kaidrop/dragdrop.py` | Dragging between the panes, with a label by the pointer |
| `kaidrop/conflict.py` | The window for a file already where another is going |
| `kaidrop/remote.py` | Browsing the server: listings (MLSD or LIST), deleting, its own thread |
| `kaidrop/logview.py` | The Log tab |
| `kaidrop/icons.py` | The file panes' icons |
| `kaidrop/settings.py` | Remembers the address and folders (never the password) |

## Legal notice

KaiDrop is an independent open-source project. It is not affiliated with,
endorsed by or sponsored by Nintendo. "Nintendo Switch" and "Switch 2" are
trademarks of their respective owners, used only to describe the hardware
this software works with. KaiDrop is a general FTP client: it copies only
the files you choose, to a server you run. See [LICENSE](LICENSE).

## License

MIT. Copyright (c) 2026 Mizuiro.
