"""Writes requirements-build.txt: every package the build and the tests need
(requirements-dev.txt and what those pull in), at exact versions, each with
the SHA-256 of every file PyPI has for that version. Installing with

    pip install --require-hashes -r requirements-build.txt

then refuses any file that isn't one of those, so a changed or swapped
package on PyPI can't get into KaiDrop.exe.

Usage: python tools/lock_requirements.py   (after changing requirements-dev.txt)
Run it with the Python the .exe is built with (pip resolves for it).
"""
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "requirements-dev.txt"
OUT = ROOT / "requirements-build.txt"


def resolve() -> list[tuple[str, str]]:
    """The packages pip would install for requirements-dev.txt, with their versions."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--dry-run", "--ignore-installed",
                        "--report", str(report), "-r", str(SOURCE)], check=True)
        data = json.loads(report.read_text(encoding="utf-8"))
    found = [(item["metadata"]["name"], item["metadata"]["version"]) for item in data["install"]]
    return sorted(found, key=lambda nv: nv[0].lower())


def hashes(name: str, version: str) -> list[str]:
    """The SHA-256 of each file (wheels and source) PyPI has for this version."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 (a fixed https URL)
        files = json.load(response)["urls"]
    return sorted(f["digests"]["sha256"] for f in files)


def main() -> None:
    lines = ["# Made by tools/lock_requirements.py from requirements-dev.txt: don't edit by hand.",
             f"# Resolved for Python {sys.version_info.major}.{sys.version_info.minor} on {sys.platform}.",
             "# pip install --require-hashes -r requirements-build.txt", ""]
    for name, version in resolve():
        digests = hashes(name, version)
        lines.append(f"{name.lower()}=={version} \\")
        lines += [f"    --hash=sha256:{d}" + (" \\" if i < len(digests) - 1 else "") for i, d in enumerate(digests)]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{OUT.name}: {sum(1 for line in lines if '==' in line)} packages")


if __name__ == "__main__":
    main()
