from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .file_logger import FileLogger, JobFileLogger

EmitFunc = Callable[[str, dict[str, Any]], None]


@dataclass
class JobContext:
    job_id: str
    _emit: EmitFunc
    _logger: JobFileLogger

    def log(self, message: str) -> None:
        rendered = str(message)
        self._logger.log(rendered)
        self._emit(
            "job.log",
            {
                "job_id": self.job_id,
                "message": rendered,
            },
        )

    def progress(self, current: int, total: int, message: str | None = None) -> None:
        self._logger.progress(current, total, message)
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "current": current,
            "total": total,
        }
        if message:
            payload["message"] = message
        self._emit("job.progress", payload)


class JobManager:
    def __init__(self, emit: EmitFunc, file_logger: FileLogger | None = None) -> None:
        self._emit = emit
        self._file_logger = file_logger or FileLogger()
        self._active_thread: threading.Thread | None = None
        self._active_job_id: str | None = None
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._active_thread is not None and self._active_thread.is_alive()

    def start(self, title: str, handler: Callable[[JobContext], Any]) -> str:
        with self._lock:
            if self.busy:
                raise RuntimeError(f"Задача уже выполняется: {self._active_job_id}")

        job_id = uuid.uuid4().hex
        job_logger = self._file_logger.create_job_logger(job_id, title)
        self._emit("job.started", {"job_id": job_id, "title": title, "log_path": job_logger.rel_path})

        def runner() -> None:
            ctx = JobContext(job_id=job_id, _emit=self._emit, _logger=job_logger)
            try:
                result = handler(ctx)
                job_logger.done(result)
                self._emit("job.done", {"job_id": job_id, "result": result, "log_path": job_logger.rel_path})
            except Exception as e:
                message = str(e)
                if len(message) > 1200:
                    message = message[:1200] + "…"
                tb = traceback.format_exc()
                job_logger.error(message, traceback_text=tb)
                self._emit(
                    "job.error",
                    {
                        "job_id": job_id,
                        "error": message,
                        "log_path": job_logger.rel_path,
                    },
                )

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        self._active_thread = thread
        self._active_job_id = job_id
        return job_id

    def wait_all(self, timeout: float = 30) -> None:
        """Wait for the active job to finish."""
        thread = self._active_thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
