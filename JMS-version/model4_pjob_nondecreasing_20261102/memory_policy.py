"""Separate SCIP accounting from an enforced process RSS ceiling (MiB)."""
SCIP_MB = 18944
PROCESS_MB = 14336
RESERVE_MB = 2048
WAIT_SECONDS = 300


def process_limit(spec):
    return float(spec.get('process_memory_mb', spec['memory_mb'] * 1.15))


def required_memory(spec, jobs=1, reserve=RESERVE_MB):
    return process_limit(spec) * jobs + reserve


def wait_message(available, required, elapsed, limit):
    return (f'WAIT_RAM available={available:.0f}MiB required={required:.0f}MiB '
            f'missing={max(0,required-available):.0f}MiB waited={elapsed:.0f}/{limit:.0f}s; ETA paused')
