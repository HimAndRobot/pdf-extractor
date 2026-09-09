import asyncio
import unittest
from pathlib import Path
import os
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from app.pdf_processing import ProcessingPool
from app.pdf_workers import PdfProcessingError


def timed_pid(kind: str, raw: bytes):
    started = time.monotonic()
    time.sleep(0.25)
    return {"pid": os.getpid(), "started": started, "finished": time.monotonic()}

class ProcessingTests(unittest.TestCase):
    def test_error_is_picklable(self):
        import pickle
        error = pickle.loads(pickle.dumps(PdfProcessingError(503, "busy")))
        self.assertEqual((error.status, error.detail), (503, "busy"))

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(ValueError): ProcessingPool(queue_timeout=0)

    def test_process_requires_explicit_start(self):
        async def run():
            pool = ProcessingPool(workers=1)
            with self.assertRaises(PdfProcessingError) as ctx:
                await pool.process("text", lambda: asyncio.sleep(0, result=b"%PDF-"))
            self.assertEqual(ctx.exception.status, 503)
        asyncio.run(run())

    def test_real_spawn_worker_processes_pdf(self):
        async def run():
            pool = ProcessingPool(workers=1, capacity=1)
            pool.start()
            try:
                raw = (Path(__file__).parents[2] / "examples" / "laudo.pdf").read_bytes()
                result = await pool.process("text", lambda: asyncio.sleep(0, result=raw))
                self.assertEqual(result["page_count"], 1)
                self.assertIn("REINI SUN", result["text"])
            finally:
                await pool.shutdown()
        asyncio.run(run())

    def test_structured_malformed_maps_to_422(self):
        async def run():
            pool = ProcessingPool(workers=1, capacity=1); pool.start()
            try:
                with self.assertRaises(PdfProcessingError) as ctx:
                    await pool.process("structured", lambda: asyncio.sleep(0, result=b"%PDF-corrupt"))
                self.assertEqual(ctx.exception.status, 422)
            finally:
                await pool.shutdown()
        asyncio.run(run())

    def test_two_spawn_workers_are_distinct_and_overlap(self):
        async def run():
            from unittest.mock import patch
            from concurrent.futures import ProcessPoolExecutor
            original_submit = ProcessPoolExecutor.submit
            def submit_timed(executor, fn, *args, **kwargs):
                return original_submit(executor, timed_pid, *args, **kwargs)
            pool = __import__("app.pdf_processing", fromlist=["ProcessingPool"]).ProcessingPool(workers=2, capacity=1)
            pool.start()
            try:
                with patch.object(ProcessPoolExecutor, "submit", submit_timed):
                    results = await asyncio.gather(*[pool.process("text", lambda: asyncio.sleep(0, result=b"raw")) for _ in range(2)])
                self.assertEqual(len({item["pid"] for item in results}), 2)
                self.assertLess(max(item["started"] for item in results), min(item["finished"] for item in results))
            finally:
                await pool.shutdown()
        asyncio.run(run())

if __name__ == "__main__": unittest.main()
