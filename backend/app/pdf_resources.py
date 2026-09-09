"""Automatic, Linux aware sizing for PDF worker resources."""
from __future__ import annotations
import math
import os
from dataclasses import dataclass

RESERVE_PER_WORKER = 256 * 1024 * 1024

@dataclass(frozen=True)
class PdfResources:
    cpus: int
    memory_bytes: int | None
    workers: int
    queue_capacity: int

def _read(path: str, reader=open) -> str | None:
    try:
        with reader(path) as f: return f.read().strip()
    except (OSError, ValueError): return None

def _cpu_count() -> int:
    count_fn = getattr(os, "process_cpu_count", None)
    if count_fn:
        value = count_fn()
        if value: return max(1, value)
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity:
        try: return max(1, len(affinity(0)))
        except OSError: pass
    return max(1, os.cpu_count() or 1)

def _quota(cpus: int, reader=open) -> int:
    raw = _read("/sys/fs/cgroup/cpu.max", reader)
    if raw:
        parts = raw.split()
        if len(parts) >= 2 and parts[0] != "max":
            try: return max(1, min(cpus, math.ceil(int(parts[0]) / int(parts[1]))))
            except (ValueError, ZeroDivisionError): pass
    q = _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", reader); p = _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us", reader)
    if q and p:
        try:
            if int(q) > 0: return max(1, min(cpus, math.ceil(int(q) / int(p))))
        except (ValueError, ZeroDivisionError): pass
    return cpus

def _memory(reader=open) -> int | None:
    limit = _read("/sys/fs/cgroup/memory.max", reader); current = _read("/sys/fs/cgroup/memory.current", reader)
    if limit and limit != "max":
        try: return max(0, int(limit) - int(current or 0))
        except ValueError: pass
    limit = _read("/sys/fs/cgroup/memory/memory.limit_in_bytes", reader); current = _read("/sys/fs/cgroup/memory/memory.usage_in_bytes", reader)
    if limit:
        try:
            value = int(limit)
            if value < (1 << 60): return max(0, value - int(current or 0))
        except ValueError: pass
    meminfo = _read("/proc/meminfo", reader)
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                try: return int(line.split()[1]) * 1024
                except (ValueError, IndexError): pass
    try: return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError): return None

def _host_memory(reader=open) -> int | None:
    meminfo = _read("/proc/meminfo", reader)
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                try: return int(line.split()[1]) * 1024
                except (ValueError, IndexError): pass
    try: return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError): return None

def detect_resources(reader=open) -> PdfResources:
    """Choose workers from CPU and the smaller cgroup/host memory budget.

    Each worker reserves roughly 256 MiB plus 25% headroom; queue capacity is
    proportional to an 8 MiB upload spool estimate (or 64 per worker when
    memory is unknown). This bounds admission without claiming a PDF's exact
    peak memory usage.
    """
    cpus = _quota(_cpu_count(), reader)
    memory = _memory(reader)
    host = _host_memory(reader)
    if memory is not None and host is not None: memory = min(memory, host)
    memory_workers = max(1, int((memory * 0.75) // RESERVE_PER_WORKER)) if memory is not None else cpus
    workers = max(1, min(cpus, memory_workers))
    queue = max(1, int(memory // (8 * 1024 * 1024))) if memory is not None else workers * 64
    return PdfResources(cpus=cpus, memory_bytes=memory, workers=workers, queue_capacity=max(1, queue))
