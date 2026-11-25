# For developers

[Back to the README](../README.md)

KaiDrop is written in Python with Tkinter. On macOS or Linux, run it from
source with Python 3.10 or later (Tkinter included):

```
pip install pypinyin anyascii      # for Chinese and other alphabets' names
python -m kaidrop
```

## Tests and building

```
pip install --require-hashes -r requirements-build.txt   # everything, pinned and checked
python -m unittest discover -s tests -t .                # tests (FTP tests need pyftpdlib)
powershell -File build.ps1                               # builds dist/KaiDrop.exe and prints its SHA-256
powershell -File build.ps1 -Out dist-test                # a test build, elsewhere
```

`requirements-dev.txt` lists what the build and tests use, at exact versions.
`requirements-build.txt` is made from it by `python tools/lock_requirements.py`
(run it after changing `requirements-dev.txt`): every package they pull in,
with the SHA-256 of each of its files on PyPI, so pip refuses anything else.
It's resolved for Windows and the Python the .exe is built with (3.13).

The .exe isn't packed with UPX (`--noupx`): antivirus programs distrust
packed programs, and the gain is small.

GitHub Actions runs the tests on Windows on every push and pull request
(`.github/workflows/tests.yml`). The selection tests need a desktop to click
in, so they are skipped there (`CI` is set) and run only on a PC.

### Signing

The .exe isn't signed yet. `build.ps1` signs it when `KAIDROP_SIGN_THUMBPRINT`
holds the thumbprint of a code-signing certificate in your certificate store
and `signtool.exe` (Windows SDK) is installed:

```
$env:KAIDROP_SIGN_THUMBPRINT = "<the certificate's thumbprint>"
powershell -File build.ps1
```

It signs with SHA-256 and an RFC 3161 timestamp (`KAIDROP_SIGN_TIMESTAMP`
changes the server; DigiCert's by default), so the signature stays valid
after the certificate expires, then checks it with `signtool verify /pa`.
Options for a certificate: an OV or EV certificate from a certificate
authority (paid, yearly), Azure Trusted Signing (paid, monthly, for
individuals in some countries), or SignPath's free plan for open-source
projects (signing then runs in their CI, not here). A self-made certificate
doesn't help: Windows doesn't trust it.

## The files

| File | What it does |
|------|--------------|
| `kaidrop/names.py` | The plain names for the console |
| `kaidrop/romanize.py` | Other alphabets in Latin letters, and whether kanji are Japanese or Chinese |
| `kaidrop/japanese.py` | Japanese in romaji: words and their readings from `kaidrop/data/readings-ja.xz` |
| `kaidrop/kana.py` | Kana in Hepburn |
| `kaidrop/hangul.py` | Korean in the Revised Romanization |
| `tools/make_readings.py` | Makes `kaidrop/data/readings-ja.xz` from UniDic's `lex.csv` |
| `tools/make_icon.py` | Makes the icon files from the Kai apps' shared icons (`make_app_icons.py`) |
| `tools/lock_requirements.py` | Makes `requirements-build.txt`, with each package's hashes |
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
| `third_party/` | The licenses of what `KaiDrop.exe` includes: Python, Tcl/Tk, tkinterdnd2, TkDND, pypinyin, anyascii, UniDic |

The version is in one place, `kaidrop/__init__.py`: the window's title and
`pyproject.toml` take it from there.
