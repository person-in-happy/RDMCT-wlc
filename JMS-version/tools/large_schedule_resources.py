"""Read-only memory telemetry and an explicitly optional physical-RAM guard."""
import ctypes
import math
import os
from ctypes import wintypes
import psutil


class PerformanceInformation(ctypes.Structure):
    # https://learn.microsoft.com/windows/win32/api/psapi/ns-psapi-performance_information
    _fields_ = [('cb',wintypes.DWORD)] + [
        (name,ctypes.c_size_t) for name in (
            'CommitTotal','CommitLimit','CommitPeak','PhysicalTotal',
            'PhysicalAvailable','SystemCache','KernelTotal','KernelPaged',
            'KernelNonpaged','PageSize')] + [
        (name,wintypes.DWORD) for name in ('HandleCount','ProcessCount','ThreadCount')]


def windows_commit():
    if os.name!='nt':
        return {}
    info=PerformanceInformation()
    info.cb=ctypes.sizeof(info)
    api=ctypes.WinDLL('psapi',use_last_error=True).GetPerformanceInfo
    api.argtypes=[ctypes.POINTER(PerformanceInformation),wintypes.DWORD]
    api.restype=wintypes.BOOL
    if not api(ctypes.byref(info),info.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    committed=int(info.CommitTotal)*int(info.PageSize)
    limit=int(info.CommitLimit)*int(info.PageSize)
    return dict(system_committed_bytes=committed,system_commit_limit_bytes=limit,
                system_commit_available_bytes=max(0,limit-committed),
                system_commit_fraction=committed/limit if limit else None,
                commit_source='GetPerformanceInfo')


def snapshot(vm=None):
    vm=psutil.virtual_memory() if vm is None else vm
    result=dict(physical_total_bytes=vm.total,physical_available_bytes=vm.available,
                physical_available_fraction=vm.available/vm.total)
    try:
        result.update(windows_commit())
    except OSError as exc:
        # Telemetry failure must not become an unrequested stopping condition.
        result['commit_read_error']=str(exc)
    return result


def policy(minimum=.25,disabled=False):
    if not math.isfinite(minimum) or not 0 <= minimum < .5:
        raise ValueError('RAM fraction must be in [0,.5); zero disables the guard')
    enabled=minimum>0 and not disabled
    return dict(memory_guard_enabled=enabled,
                min_available_fraction=minimum if enabled else 0.,
                memory_policy=('native_unlimited_with_system_available_fraction' if enabled
                               else 'native_unlimited_observe_only'),
                fixed_scip_memory_mb=None,fixed_process_rss_mb=None)


def should_stop(settings,sample):
    threshold=settings['min_available_fraction']
    enabled=settings.get('memory_guard_enabled',threshold>0)
    return bool(enabled and threshold>0 and sample['physical_available_fraction']<threshold)


def pressure(sample):
    return (sample['physical_available_fraction']<.25 or
            (sample.get('system_commit_fraction') or 0)>=.9)


def describe(sample):
    physical=f'RAM_available={sample["physical_available_bytes"]/1024**3:.2f}GiB'
    if 'system_committed_bytes' not in sample:
        return physical+' commit=unknown'
    return (physical+
            f' system_commit={sample["system_committed_bytes"]/1024**3:.2f}/'
            f'{sample["system_commit_limit_bytes"]/1024**3:.2f}GiB')
