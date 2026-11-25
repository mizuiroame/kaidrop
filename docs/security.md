# Security

[Back to the README](../README.md) · How to report a problem: [SECURITY.md](../SECURITY.md)

## The console's password

- **KaiDrop never saves the FTP password.** You type it each time you
  connect, and it's kept only in memory while KaiDrop is open.
- **What it does save**, in `%APPDATA%\KaiDrop\settings.json` (as plain
  text, readable by anyone who can open your user's files): the console's
  address, port and user name, the folders you used last, and whether
  **Plain names for Switch 2** is on.
- **FTP sends the password in clear text.** The console's FTP servers
  (OunceShell's, ftpd and the like) and SW2Transfer's API don't offer
  encryption, so the user name, the password and the files cross your
  network unencrypted, as with any FTP client: anyone on the same network who
  watches its traffic can read them. Use KaiDrop on your home network only,
  and don't reuse that password for anything else.

## What KaiDrop connects to

Only the console at the address you type: its FTP server, and SW2Transfer's
API on the same address (port 6967) when it runs there. Nothing about you is
sent anywhere else. [SECURITY.md](../SECURITY.md) says how KaiDrop treats
what the server sends (listings and files are untrusted).

## The .exe

- Built with PyInstaller from this repository, with every package pinned to
  an exact version and the SHA-256 of its files
  (`requirements-build.txt`, installed with `pip install --require-hashes`):
  a changed or swapped package on PyPI can't get in.
- Not packed with UPX: packed programs look suspicious to antivirus
  programs, and it saves little.
- Not signed yet, so Windows SmartScreen may warn the first time. The build
  can sign it once there's a code-signing certificate
  (see [For developers](developers.md#signing)).
- Each release's notes give the file's SHA-256: check it in PowerShell with
  `Get-FileHash KaiDrop.exe`.
