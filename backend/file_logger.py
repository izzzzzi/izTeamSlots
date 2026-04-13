from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import DATA_ROOT


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def _safe_title(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip().lower())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "job"


class FileLogger:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (DATA_ROOT / "logs")
        self.jobs_dir = self.root / "jobs"
        self.app_log = self.root / "app.log"
        self._lock = threading.Lock()
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _append(self, path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                for line in lines:
                    fh.write(line.rstrip("\n") + "\n")

    def info(self, message: str) -> None:
        self._append(self.app_log, [f"[{_timestamp()}] INFO  {message}"])

    def error(self, message: str, traceback_text: str | None = None) -> None:
        lines = [f"[{_timestamp()}] ERROR {message}"]
        if traceback_text:
            lines.extend(traceback_text.rstrip().splitlines())
        self._append(self.app_log, lines)

    def create_job_logger(self, job_id: str, title: str) -> "JobFileLogger":
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"{stamp}-{job_id[:8]}-{_safe_title(title)}.log"
        path = self.jobs_dir / filename
        rel_path = path.relative_to(DATA_ROOT).as_posix()
        logger = JobFileLogger(path=path, rel_path=rel_path, title=title, root_logger=self)
        logger.log(f"JOB START: {title}")
        self.info(f"Job created: {title} [{job_id}] -> {rel_path}")
        return logger


@dataclass
class JobFileLogger:
    path: Path
    rel_path: str
    title: str
    root_logger: FileLogger

    def log(self, message: str) -> None:
        self.root_logger._append(self.path, [f"[{_timestamp()}] {message}"])

    def progress(self, current: int, total: int, message: str | None = None) -> None:
        suffix = f" {message}" if message else ""
        self.log(f"PROGRESS {current}/{total}{suffix}")

    def done(self, result: Any) -> None:
        rendered = json.dumps(result, ensure_ascii=False, default=str) if result is not None else "null"
        self.log(f"JOB DONE: {rendered}")

    def error(self, message: str, traceback_text: str | None = None) -> None:
        lines = [f"[{_timestamp()}] JOB ERROR: {message}"]
        if traceback_text:
            lines.extend(traceback_text.rstrip().splitlines())
        self.root_logger._append(self.path, lines)
        self.root_logger.error(f"{self.title}: {message}", traceback_text=traceback_text)
