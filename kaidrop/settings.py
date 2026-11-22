"""The connection and folder used last time (never the password). The
connection fields start empty: only what the user typed is remembered."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Settings:
    host: str = ""
    port: str = ""
    user: str = ""
    remote_folder: str = "/"
    plain_names: bool = True
    local_folder: str = ""


def _path() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "KaiDrop" / "settings.json"


def load() -> Settings:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):  # "[]" or "null" is valid JSON but not settings.
        return Settings()
    defaults = Settings()
    return Settings(
        host=str(data.get("host", defaults.host)),
        port=str(data.get("port", defaults.port)),
        user=str(data.get("user", defaults.user)),
        remote_folder=str(data.get("remote_folder", defaults.remote_folder)),
        plain_names=bool(data.get("plain_names", defaults.plain_names)),
        local_folder=str(data.get("local_folder", defaults.local_folder)),
    )


def save(settings: Settings) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except OSError:
        pass  # Not being able to remember settings isn't worth stopping for.
