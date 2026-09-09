"""Bounded asynchronous admission around a persistent process pool."""
from __future__ import annotations
import asyncio
import os
import math
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context
from typing import Awaitable, Callable, Any
from .pdf_workers import process_pdf, PdfProcessingError
from .pdf_resources import detect_resources


def _positive(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


class ProcessingPool:
    def __init__(self, workers: int | None = None, capacity: int | None = None, queue_timeout: float | None = None, response_timeout: float | None = None):
        resources = detect_resources() if workers is None or capacity is None else None
        self.workers = _positive(workers if workers is not None else resources.workers, "workers")
        self.capacity = _positive(capacity if capacity is not None else resources.queue_capacity, "capacity")
        self.queue_timeout = float(queue_timeout if queue_timeout is not None else 30)
        self.response_timeout = float(response_timeout if response_timeout is not None else 60)
        if not math.isfinite(self.queue_timeout) or self.queue_timeout <= 0 or not math.isfinite(self.response_timeout) or self.response_timeout <= 0:
            raise ValueError("processing timeouts must be finite and positive")
        self._active = asyncio.Semaphore(self.workers)
        self._pool: ProcessPoolExecutor | None = None
        self._admitted = 0

    def start(self):
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self.workers, mp_context=get_context("spawn"))

    async def shutdown(self):
        pool = self._pool; self._pool = None
        if pool:
            await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=True)

    def _recover_broken(self, failed: ProcessPoolExecutor) -> None:
        """Replace only the pool that actually failed; never retry its job."""
        if self._pool is not failed:
            return
        self._pool = ProcessPoolExecutor(max_workers=self.workers, mp_context=get_context("spawn"))
        asyncio.create_task(asyncio.to_thread(failed.shutdown, wait=False, cancel_futures=True))

    async def process(self, kind: str, loader_async: Callable[[], Awaitable[bytes]]) -> dict:
        if self._admitted >= self.workers + self.capacity:
            raise PdfProcessingError(503, "O processamento está ocupado; tente novamente.")
        self._admitted += 1
        active_acquired = False
        submitted = False
        try:
            try:
                await asyncio.wait_for(self._active.acquire(), timeout=self.queue_timeout)
                active_acquired = True
            except asyncio.TimeoutError as exc:
                raise PdfProcessingError(503, "A fila de processamento excedeu o tempo de espera.") from exc
            try:
                raw = await loader_async()
                if self._pool is None:
                    raise PdfProcessingError(503, "O processamento ainda não foi iniciado.")
                pool = self._pool
                try:
                    future = pool.submit(process_pdf, kind, raw)
                except BrokenProcessPool as exc:
                    self._recover_broken(pool)
                    raise PdfProcessingError(503, "O processamento ficou indisponível; tente novamente.") from exc
                submitted = True
                loop = asyncio.get_running_loop()
                def release(_future):
                    try:
                        error = _future.exception()
                    except BaseException:
                        error = None
                    if isinstance(error, BrokenProcessPool) or (error is not None and "BrokenProcessPool" in type(error).__name__):
                        loop.call_soon_threadsafe(self._recover_broken, pool)
                    loop.call_soon_threadsafe(self._finish, active_acquired)
                future.add_done_callback(release)
                wrapped = asyncio.wrap_future(future)
                def consume_wrapped(done):
                    try:
                        done.exception()
                    except BaseException:
                        pass
                wrapped.add_done_callback(consume_wrapped)
                try:
                    return await asyncio.wait_for(asyncio.shield(wrapped), timeout=self.response_timeout)
                except asyncio.TimeoutError as exc:
                    raise PdfProcessingError(504, "O processamento excedeu o tempo limite.") from exc
                except Exception as exc:
                    if isinstance(exc, BrokenProcessPool) or "BrokenProcessPool" in type(exc).__name__:
                        self._recover_broken(pool)
                        raise PdfProcessingError(503, "O processamento ficou indisponível; tente novamente.") from exc
                    raise
            finally:
                if not submitted and active_acquired:
                    self._active.release()
        finally:
            if not submitted:
                self._admitted -= 1

    def _finish(self, active: bool) -> None:
        if active:
            self._active.release()
        self._admitted -= 1
