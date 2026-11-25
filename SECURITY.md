# Security policy

## Supported versions

Only the [latest release](https://github.com/mizuiroame/kaidrop/releases/latest)
gets security fixes. Please check that a problem still happens with it before
reporting.

## Reporting a vulnerability

Please don't open a public issue for a security problem. Report it privately
instead: on this repository's **Security** tab, choose **Report a
vulnerability**. Say which version you used, what you did and what happened,
and, if you can, the FTP server's answers that show it (a listing, a file
name).

KaiDrop is a hobby project kept by one person. Reports are read and answered
as time allows; once a fix is released, the report can be made public, and
you're credited in the release notes unless you'd rather not be.

## Scope

In scope: KaiDrop's own code and how it uses its libraries. For instance, an
FTP server's listing or file that can make KaiDrop write, delete or overwrite
files outside the folders you chose, on the PC or on the console, fill the
disk, run something, or crash.

Out of scope: the FTP servers on the console (ftpd, sys-ftpd and the like),
Windows itself, and bugs that belong to Python or a bundled library alone
(please report those upstream too; KaiDrop updates them when there's a fix).

## How KaiDrop handles your data

- **What it connects to.** Only the console at the address you type: its FTP
  server, and, when a batch starts, SW2Transfer's API on the same address
  (port 6967), if it runs there. Nothing else, and nothing about you is sent
  anywhere.
- **Plain FTP and HTTP.** The console's FTP servers and SW2Transfer's API
  don't offer encryption, so the user name, the password and the files travel
  unencrypted on your network, as with any FTP client. Use it on your home
  network only. SW2Transfer gets the FTP password only when it asks for one
  (it then answers with a sign-in token for the rest of the batch).
- **The password is never saved.** `%APPDATA%\KaiDrop\settings.json` keeps
  only the address, port, user name and folders used last time, and the
  file-name choice.

## Untrusted input

An FTP server decides what its listings say, so KaiDrop doesn't trust them:

- Entries named `.`, `..` or with `/` or `\` in them are left out, and walking,
  deleting or copying folders stops 32 levels deep, so a listing can't make
  KaiDrop climb out of a folder or go on forever.
- A download stops past the size the server gave (plus 1 MB), and one of
  unknown size stops when the disk gets below 1 GB free. Through SW2Transfer,
  the size it gives is checked the same way before anything comes.
- SW2Transfer is used only when it shows the same folders as the FTP server,
  so its paths are the same card's.
- Names are made safe for Windows: characters it doesn't allow become `_`,
  reserved names (`CON`, `COM1`, `COM¹`...) get a `_`, characters that turn
  text around (which can make a program's name look like a song's) are
  dropped, and names that would end up the same get `(2)`.
- A file arrives as `name.kaidrop-part` and gets its name only when it's
  whole, so a stopped download never looks complete or replaces a file of
  yours.
- **Open** asks before opening a downloaded program, script or shortcut.

## The release

- `KaiDrop.exe` is built with PyInstaller from this repository (see
  [docs/developers.md](docs/developers.md)), without UPX. It isn't signed
  yet, so Windows SmartScreen may warn the first time; the build is ready to
  sign it once there's a certificate.
- Each release's notes give the file's SHA-256. Check it in PowerShell with
  `Get-FileHash KaiDrop.exe`.
- The build's dependencies, and theirs, are pinned to exact versions with the
  SHA-256 of their files in `requirements-build.txt`, installed with
  `pip install --require-hashes`.
