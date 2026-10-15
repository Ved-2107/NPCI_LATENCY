"""Asynchronous background worker and job execution tracker for HTTP 202 patterns."""
import concurrent.futures
import threading
import time
import uuid
from typing import Callable, Optional


class JobManager:
    def __init__(self, max_workers: int = 4):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="remit-worker")
        self._jobs: dict[str, dict] = {}
        self._lock = threading.RLock()

    def submit(self, fn: Callable, *args, **kwargs) -> str:
        job_id = "job_" + uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._jobs[job_id] = {
                "jobId": job_id,
                "status": "QUEUED",
                "result": None,
                "error": None,
                "submittedAt": now,
                "startedAt": None,
                "completedAt": None,
            }

        def worker():
            with self._lock:
                self._jobs[job_id]["status"] = "RUNNING"
                self._jobs[job_id]["startedAt"] = time.time()
            try:
                res = fn(*args, **kwargs)
                with self._lock:
                    self._jobs[job_id]["status"] = "COMPLETED"
                    self._jobs[job_id]["result"] = res
                    self._jobs[job_id]["completedAt"] = time.time()
            except Exception as e:
                with self._lock:
                    self._jobs[job_id]["status"] = "FAILED"
                    self._jobs[job_id]["error"] = str(e)
                    self._jobs[job_id]["completedAt"] = time.time()

        self._executor.submit(worker)
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


# Global job manager instance
job_manager = JobManager()
