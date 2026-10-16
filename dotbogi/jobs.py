"""오래 걸리는 계산을 백그라운드 스레드로 돌리고 진행률을 알려준다."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from .io import LoadError


class Job:
    def __init__(self, kind: str, label: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.state = "running"  # running | done | error
        self.progress = 0.0
        self.message = "시작하는 중"
        self.result = None
        self.error: str | None = None
        self.detail: str | None = None
        self.started = time.time()
        self.finished: float | None = None

    def update(self, progress: float, message: str | None = None) -> None:
        self.progress = max(0.0, min(1.0, float(progress)))
        if message:
            self.message = message

    def to_dict(self, with_result: bool = True) -> dict:
        d = {"id": self.id, "kind": self.kind, "label": self.label, "state": self.state,
             "progress": self.progress, "message": self.message, "error": self.error,
             "elapsed": (self.finished or time.time()) - self.started}
        if with_result and self.state == "done":
            d["result"] = self.result
        return d


class JobManager:
    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dotbogi-job")
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def submit(self, kind: str, label: str, fn, *args, **kwargs) -> Job:
        """같은 종류의 작업이 돌고 있으면 새로 만들지 않고 그걸 돌려준다."""
        with self.lock:
            for j in self.jobs.values():
                if j.kind == kind and j.state == "running":
                    return j
            job = Job(kind, label)
            self.jobs[job.id] = job
            self._trim()

        def run():
            try:
                job.result = fn(job, *args, **kwargs)
                job.progress = 1.0
                job.message = "완료"
                job.state = "done"
            except (LoadError, ValueError, KeyError, FileNotFoundError) as e:
                job.error = str(e) if not isinstance(e, KeyError) else f"찾을 수 없음: {e}"
                job.state = "error"
            except MemoryError:
                job.error = "메모리가 부족합니다. 데이터를 줄이거나 다른 프로그램을 닫고 다시 해 보세요."
                job.state = "error"
            except Exception as e:  # 예상 못 한 오류도 화면에 보여준다
                job.error = f"예상하지 못한 오류: {type(e).__name__}: {e}"
                job.detail = traceback.format_exc()
                job.state = "error"
            finally:
                job.finished = time.time()

        self.pool.submit(run)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def running(self) -> list[Job]:
        return [j for j in self.jobs.values() if j.state == "running"]

    def _trim(self, keep: int = 60) -> None:
        if len(self.jobs) <= keep:
            return
        done = sorted((j for j in self.jobs.values() if j.state != "running"), key=lambda j: j.started)
        for j in done[: len(self.jobs) - keep]:
            self.jobs.pop(j.id, None)
