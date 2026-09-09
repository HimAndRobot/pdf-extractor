import unittest
from unittest.mock import patch
from app.pdf_resources import detect_resources

class ResourceDetectorTests(unittest.TestCase):
    def reader(self, values):
        def read(path):
            class C:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self): return values.get(path, "")
            return C()
        return read

    def test_quota_ceil_and_memory_zero(self):
        vals={"/sys/fs/cgroup/cpu.max":"250000 100000", "/sys/fs/cgroup/memory.max":"0", "/sys/fs/cgroup/memory.current":"0"}
        with patch("app.pdf_resources.os.process_cpu_count", return_value=64, create=True):
            r=detect_resources(self.reader(vals))
        self.assertEqual(r.cpus,3); self.assertEqual(r.workers,1)

    def test_min_host_and_cgroup_memory_and_queue(self):
        gib=1024**3
        vals={"/sys/fs/cgroup/cpu.max":"100000 100000", "/sys/fs/cgroup/memory.max":str(4*gib), "/sys/fs/cgroup/memory.current":"0", "/proc/meminfo":f"MemAvailable: {gib//1024} kB"}
        r=detect_resources(self.reader(vals)); self.assertEqual(r.workers,1); self.assertGreaterEqual(r.queue_capacity,20)

    def test_64_cpus_not_artificially_capped(self):
        vals={"/sys/fs/cgroup/cpu.max":"max 100000", "/proc/meminfo":f"MemAvailable: {64*1024*1024} kB"}
        with patch("app.pdf_resources.os.process_cpu_count", return_value=64, create=True):
            r=detect_resources(self.reader(vals))
        self.assertEqual(r.cpus,64); self.assertEqual(r.workers,64)

    def test_missing_files_falls_back_and_unlimited_cgroup_ignored(self):
        vals={"/sys/fs/cgroup/cpu.max":"max 100000", "/sys/fs/cgroup/memory.max":"max", "/proc/meminfo":"MemAvailable: 1024 kB"}
        with patch("app.pdf_resources.os.process_cpu_count", return_value=2, create=True):
            r=detect_resources(self.reader(vals))
        self.assertEqual(r.cpus,2); self.assertEqual(r.workers,1)

if __name__ == "__main__": unittest.main()
