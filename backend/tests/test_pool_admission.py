import asyncio
import unittest
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from types import SimpleNamespace
from unittest.mock import patch

from app.pdf_processing import ProcessingPool
from app.pdf_workers import PdfProcessingError


class FakeExecutor:
    def __init__(self, future=None, error=None):
        self.future = future or Future()
        self.error = error
        self.calls = 0

    def submit(self, *_args):
        self.calls += 1
        if self.error:
            raise self.error
        return self.future

    def shutdown(self, **_kwargs):
        return None


class PoolAdmissionTests(unittest.TestCase):
    def test_queue_full_does_not_call_loader(self):
        async def run():
            pool = ProcessingPool(workers=1, capacity=1, queue_timeout=0.02, response_timeout=1)
            pool._pool = FakeExecutor()
            first_loader = lambda: asyncio.sleep(0, result=b"%PDF-1")
            second_called = False
            async def second_loader():
                nonlocal second_called
                second_called = True
                return b"%PDF-1"
            first = asyncio.create_task(pool.process("text", first_loader))
            await asyncio.sleep(0.005)
            second = asyncio.create_task(pool.process("text", second_loader))
            await asyncio.sleep(0.005)
            third = asyncio.create_task(pool.process("text", second_loader))
            with self.assertRaises(PdfProcessingError) as error:
                await third
            self.assertEqual(error.exception.status, 503)
            self.assertFalse(second_called)
            pool._pool.future.set_result({"page_count": 1, "text": "x", "pages": []})
            await first
            result = await second
            self.assertEqual(result["page_count"], 1)
        asyncio.run(run())

    def test_timeout_keeps_slot_until_underlying_future_finishes(self):
        async def run():
            future = Future(); executor = FakeExecutor(future)
            pool = ProcessingPool(workers=1, capacity=1, queue_timeout=0.03, response_timeout=0.01)
            pool._pool = executor
            first = asyncio.create_task(pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1")))
            await asyncio.sleep(0.003)
            with self.assertRaises(PdfProcessingError) as error:
                await first
            self.assertEqual(error.exception.status, 504)
            self.assertEqual(executor.calls, 1)
            with self.assertRaises(PdfProcessingError) as queued:
                await pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1"))
            self.assertEqual(queued.exception.status, 503)
            future.set_result({"page_count": 1, "text": "x", "pages": []})
            await asyncio.sleep(0.01)
            self.assertEqual(pool._admitted, 0)
        asyncio.run(run())

    def test_cancelled_running_job_keeps_slot_until_future_finishes(self):
        async def run():
            future = Future(); executor = FakeExecutor(future)
            pool = ProcessingPool(workers=1, capacity=1, response_timeout=1); pool._pool = executor
            task = asyncio.create_task(pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1")))
            await asyncio.sleep(0.003); task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertEqual(pool._admitted, 1)
            future.set_result({"page_count": 1, "text": "x", "pages": []}); await asyncio.sleep(0.01)
            self.assertEqual(pool._admitted, 0)
        asyncio.run(run())

    def test_cancelled_queued_job_releases_its_admission(self):
        async def run():
            future = Future(); executor = FakeExecutor(future)
            pool = ProcessingPool(workers=1, capacity=1, queue_timeout=1); pool._pool = executor
            first = asyncio.create_task(pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1")))
            await asyncio.sleep(0.003)
            second = asyncio.create_task(pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1")))
            await asyncio.sleep(0.003); second.cancel()
            with self.assertRaises(asyncio.CancelledError): await second
            self.assertEqual(pool._admitted, 1)
            future.set_result({"page_count": 1, "text": "x", "pages": []}); await first; await asyncio.sleep(0.01)
            self.assertEqual(pool._admitted, 0)
        asyncio.run(run())

    def test_loader_error_releases_admission(self):
        async def run():
            executor = FakeExecutor(); pool = ProcessingPool(workers=1, capacity=1)
            pool._pool = executor
            async def fail(): raise RuntimeError("loader")
            with self.assertRaises(RuntimeError): await pool.process("text", fail)
            self.assertEqual(pool._admitted, 0)
        asyncio.run(run())

    def test_broken_submit_recovers_pool_without_retrying_job(self):
        async def run():
            failed = FakeExecutor(error=BrokenProcessPool())
            pool = ProcessingPool(workers=1, capacity=1); pool._pool = failed
            replacement = FakeExecutor()
            with patch("app.pdf_processing.ProcessPoolExecutor", return_value=replacement):
                with self.assertRaises(PdfProcessingError) as error:
                    await pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1"))
            self.assertEqual(error.exception.status, 503)
            self.assertIs(pool._pool, replacement)
            self.assertEqual(failed.calls, 1)
            self.assertEqual(replacement.calls, 0)
        asyncio.run(run())

    def test_broken_await_recovers_pool_without_retrying_job(self):
        async def run():
            failed = FakeExecutor(); pool = ProcessingPool(workers=1, capacity=1); pool._pool = failed
            replacement = FakeExecutor()
            with patch("app.pdf_processing.ProcessPoolExecutor", return_value=replacement):
                task = asyncio.create_task(pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1")))
                await asyncio.sleep(0.003); failed.future.set_exception(BrokenProcessPool())
                with self.assertRaises(PdfProcessingError) as error: await task
            self.assertEqual(error.exception.status, 503); self.assertIs(pool._pool, replacement)
            self.assertEqual(failed.calls, 1); self.assertEqual(replacement.calls, 0)
        asyncio.run(run())

    def test_late_failure_after_timeout_is_consumed_and_releases_slot(self):
        async def run():
            future = Future(); pool = ProcessingPool(workers=1, capacity=1, response_timeout=0.01); pool._pool = FakeExecutor(future)
            with self.assertRaises(PdfProcessingError): await pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-1"))
            future.set_exception(RuntimeError("late worker error")); await asyncio.sleep(0.01)
            self.assertEqual(pool._admitted, 0)
        asyncio.run(run())

    def test_pool_uses_detected_capacity_without_artificial_32_cap(self):
        resources = SimpleNamespace(workers=40, queue_capacity=160)
        with patch("app.pdf_processing.detect_resources", return_value=resources):
            pool = ProcessingPool()
        self.assertEqual(pool.workers, 40)
        self.assertEqual(pool.capacity, 160)


if __name__ == "__main__":
    unittest.main()
