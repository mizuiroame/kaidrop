# For developers

[Back to the README](../README.md)

KaiDrop is written in Python with Tkinter. On macOS or Linux, run it from
source with Python 3.10 or later (Tkinter included):

```
python -m kaidrop
```

## Tests and building

```
python -m unittest discover -s tests -t .          # tests (FTP tests need pyftpdlib)
pip install -r requirements-dev.txt                # pyftpdlib and PyInstaller
powershell -File build.ps1                         # builds dist/KaiDrop.exe
```

## The files

| File | What it does |
|------|--------------|
| `kaidrop/names.py` | The plain names for the console |
| `kaidrop/playlists.py` | Playlists' copies for the console, pointing to the songs' plain names |
| `kaidrop/plan.py` | What to send where: the files and their names on the console |
| `kaidrop/ftp.py` | Sending: folders, files already there, `.part` until complete, cancel |
| `kaidrop/download.py` | Receiving: what comes where, names Windows allows, `.part` until complete |
| `kaidrop/sw2.py` | SW2Transfer's HTTP API: finding it, signing in, files in chunks over 8 connections (both ways) |
| `kaidrop/batch.py` | A batch in the queue, and what's left of it to continue after Reconnect |
| `kaidrop/rate.py` | The speed and time left |
| `kaidrop/app.py` | The window: connection, the two panes, transfers, log |
| `kaidrop/panes.py` | The file panes: this computer and the server, right-click menus, selection |
| `kaidrop/foldertree.py` | This computer's folder tree, like Explorer's |
| `kaidrop/places.py` | Where the tree starts: Desktop, Documents… and the drives, by name |
| `kaidrop/dragdrop.py` | Dragging between the panes (or onto a server folder), with a label by the pointer |
| `kaidrop/serverops.py` | Moving and copying on the server itself (cut, copy and paste) |
| `kaidrop/conflict.py` | The window for a file already where another is going |
| `kaidrop/remote.py` | Browsing the server: listings (MLSD or LIST), deleting, its own thread |
| `kaidrop/logview.py` | The Log tab |
| `kaidrop/icons.py` | The file panes' icons |
| `kaidrop/settings.py` | Remembers the address and folders (never the password) |
| `third_party/` | The licenses of what `KaiDrop.exe` includes: Python, Tcl/Tk, tkinterdnd2, TkDND |

The version is in one place, `kaidrop/__init__.py`: the window's title and
`pyproject.toml` take it from there.
