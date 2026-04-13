from __future__ import annotations

import threading
import time
import unittest
from typing import Any
from uuid import uuid4

from backend import DATA_ROOT
from backend.file_logger import FileLogger
from backend.jobs import JobManager


class TestJobManager(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.logs_root = DATA_ROOT / "downloaded_files" / f"test-logs-{uuid4().hex}"
        self.logger = FileLogger(self.logs_root)

    def tearDown(self) -> None:
        if self.logs_root.exists():
            for child in sorted(self.logs_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()

    def emit(self, event: str, data: dict[str, Any]) -> None:
        self.events.append((event, data))

    def test_successful_job_emits_started_progress_done(self) -> None:
        manager = JobManager(self.emit, file_logger=self.logger)

        def handler(ctx):
            ctx.log("hello")
            ctx.progress(1, 2, "step")
            return {"ok": True}

        job_id = manager.start("test job", handler)
        manager.wait_all()

        event_names = [name for name, _ in self.events]
        self.assertEqual(job_id, self.events[0][1]["job_id"])
        self.assertIn("job.started", event_names)
        self.assertIn("job.log", event_names)
        self.assertIn("job.progress", event_names)
        self.assertIn("job.done", event_names)

    def test_failed_job_emits_error(self) -> None:
        manager = JobManager(self.emit, file_logger=self.logger)

        def handler(_ctx):
            raise RuntimeError("boom")

        manager.start("failing job", handler)
        manager.wait_all()

        last_event, payload = self.events[-1]
        self.assertEqual(last_event, "job.error")
        self.assertEqual(payload["error"], "boom")

    def test_cannot_start_second_job_while_busy(self) -> None:
        manager = JobManager(self.emit, file_logger=self.logger)
        release = threading.Event()

        def handler(_ctx):
            release.wait(timeout=2)
            time.sleep(0.05)

        manager.start("long job", handler)
        try:
            with self.assertRaises(RuntimeError):
                manager.start("second job", handler)
        finally:
            release.set()
            manager.wait_all()

    def test_start_is_thread_safe_under_contention(self) -> None:
        """Ensure only one job starts even with concurrent start() calls."""
        manager = JobManager(self.emit, file_logger=self.logger)
        barrier = threading.Barrier(10)
        release = threading.Event()
        results: list[str | None] = [None] * 10
        errors: list[str | None] = [None] * 10

        def handler(_ctx):
            release.wait(timeout=5)

        def try_start(index: int) -> None:
            barrier.wait()
            try:
                job_id = manager.start(f"job-{index}", handler)
                results[index] = job_id
            except RuntimeError as e:
                errors[index] = str(e)

        threads = [threading.Thread(target=try_start, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        release.set()
        manager.wait_all()

        started = [r for r in results if r is not None]
        failed = [e for e in errors if e is not None]
        self.assertEqual(len(started), 1, f"Expected exactly 1 job to start, got {len(started)}")
        self.assertEqual(len(failed), 9, f"Expected 9 rejections, got {len(failed)}")
