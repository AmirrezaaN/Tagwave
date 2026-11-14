"""Background jobs with progress reporting and cancellation."""

from __future__ import annotations

import itertools
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from .core.errors import TagwaveError


def error_json(exc: BaseException) -> dict:
    if isinstance(exc, TagwaveError):
        return exc.to_json()
    if isinstance(exc, PermissionError):
        return {"code": "permission", "message": str(exc), "details": {}}
    if isinstance(exc, FileNotFoundError):
        return {"code": "not-found", "message": str(exc), "details": {}}
    if isinstance(exc, OSError):
        return {"code": "io", "message": str(exc), "details": {}}
    return {"code": "error", "message": "%s: %s" % (type(exc).__name__, exc), "details": {}}


class Job:
    def __init__(self, manager: "JobManager", job_id: str, kind: str, meta: dict):
        self.manager = manager
        self.id = job_id
        self.kind = kind
        self.meta = meta
        self.state = "running"
        self.progress = 0.0
        self.message = ""
        self.result = None
        self.error = None
        self.cancel_event = threading.Event()
        self._last_emit = 0.0

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def set_progress(self, fraction: float, message: str = "", force: bool = False) -> None:
        self.progress = max(0.0, min(1.0, float(fraction)))
        if message:
            self.message = message
        now = time.monotonic()
        if force or now - self._last_emit > 0.1:
            self._last_emit = now
            self.manager.emit(self)

    def event(self, kind: str, data) -> None:
        payload = {"jobId": self.id}
        payload.update(data)
        self.manager.bus.publish(kind, payload)

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "state": self.state, "progress": self.progress,
                "message": self.message, "result": self.result, "error": self.error, "meta": self.meta}


class JobManager:
    def __init__(self, bus, workers: int = 4):
        self.bus = bus
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._jobs: dict = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def emit(self, job: Job) -> None:
        self.bus.publish("job", job.to_json())

    def start(self, kind: str, fn, *args, meta: dict | None = None) -> str:
        job = Job(self, "j%d" % next(self._ids), kind, meta or {})
        with self._lock:
            self._jobs[job.id] = job
            # keep memory bounded
            if len(self._jobs) > 200:
                for jid in [j for j, v in self._jobs.items() if v.state != "running"][:100]:
                    self._jobs.pop(jid, None)
        self.emit(job)
        self._pool.submit(self._run, job, fn, args)
        return job.id

    def _run(self, job: Job, fn, args) -> None:
        try:
            job.result = fn(job, *args)
            job.state = "cancelled" if job.cancelled else "done"
            job.progress = 1.0
        except BaseException as exc:  # noqa: BLE001 - report everything to the UI
            if job.cancelled:
                job.state = "cancelled"
            else:
                job.state = "error"
                job.error = error_json(exc)
                if not isinstance(exc, TagwaveError):
                    traceback.print_exc()
        self.emit(job)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job and job.state == "running":
            job.cancel_event.set()
            return True
        return False

    def shutdown(self) -> None:
        with self._lock:
            for j in self._jobs.values():
                j.cancel_event.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
