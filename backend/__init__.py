import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_data_root() -> Path:
    env = os.environ.get("IZTEAMSLOTS_DATA")
    if env:
        return Path(env)
    if "node_modules" in str(PROJECT_ROOT):
        return Path.home() / ".izteamslots"
    return PROJECT_ROOT


DATA_ROOT = _resolve_data_root()
