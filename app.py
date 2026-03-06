from __future__ import annotations

import os
import subprocess
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    ui_dir = root / "ui"

    if not ui_dir.exists():
        raise RuntimeError("ui/ не найден")

    bun_bin = os.environ.get("BUN_BIN", "bun")
    env = {
        **os.environ,
        "IZTEAMSLOTS_AUTOMIGRATE_PROFILES": os.environ.get("IZTEAMSLOTS_AUTOMIGRATE_PROFILES", "0"),
    }
    cmd = [bun_bin, "run", "src/main.ts"]
    return subprocess.call(cmd, cwd=ui_dir, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
