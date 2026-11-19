"""Limit this Windows process's committed memory, including native libraries."""
import ctypes
from ctypes import wintypes
import os
import time

import psutil


CAP_MIB = 1024
RESERVE_MIB = 2048
MIB = 1024**2


def limit_process():
    if os.name != "nt":
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        caps = [CAP_MIB*MIB] + [v for v in (soft, hard) if v != resource.RLIM_INFINITY]
        resource.setrlimit(resource.RLIMIT_AS, (min(caps), hard))
        return None
    size = ctypes.c_size_t
    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_ws", size), ("max_ws", size),
                    ("active", wintypes.DWORD), ("affinity", size),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io_counts", ctypes.c_uint64*6), ("process_limit", size),
                    ("job_limit", size), ("peak_process", size), ("peak_job", size)]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    job = api.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = Extended()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.process_limit = CAP_MIB*MIB
    if not (api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            and api.AssignProcessToJobObject(job, wintypes.HANDLE(-1))):
        error = ctypes.get_last_error()
        api.CloseHandle(job)
        raise ctypes.WinError(error)
    return job  # Retain this private job handle until this process exits.


def sample():
    info = psutil.Process().memory_info()
    return dict(rss_mib=round(info.rss/MIB, 2),
                peak_rss_mib=round(getattr(info, "peak_wset", info.rss)/MIB, 2),
                available_mib=round(psutil.virtual_memory().available/MIB, 2))


def wait_for_headroom():
    while psutil.virtual_memory().available < (CAP_MIB+RESERVE_MIB)*MIB:
        print(f"Waiting for {CAP_MIB+RESERVE_MIB} MiB free RAM | {sample()} | ETA unknown", flush=True)
        time.sleep(5)


def peers():
    found = []
    for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
        if not (p.info["name"] or "").lower().startswith("python") or p.pid == os.getpid():
            continue
        scripts = [arg for arg in (p.info["cmdline"] or []) if arg.endswith(".py")]
        if scripts and p.info["memory_info"]:
            found.append(dict(pid=p.pid, script=scripts[0], rss_mib=round(p.info["memory_info"].rss/MIB, 2)))
    return found
