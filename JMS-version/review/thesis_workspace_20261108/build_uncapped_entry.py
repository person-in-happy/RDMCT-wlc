"""Create an isolated driver; never edits an existing experiment launcher."""
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[3]
source=ROOT/'JMS-version/tools/default_gap_experiments.py'
target=ROOT/'JMS-version/tools/thesis_gap_experiments.py'
code=source.read_text(encoding='utf-8')
origin=hashlib.sha256(source.read_bytes()).hexdigest()

def replace(old,new,count=1):
    global code
    assert code.count(old)==count,(old[:90],code.count(old))
    code=code.replace(old,new)

replace('Isolated D-configuration gap experiments; plan/prepare/check do not optimize.',
        'Thesis D gap experiments with no fixed SCIP/process memory quota.\n\nplan/prepare/check do not optimize. New campaigns only; frozen old campaigns\nare intentionally incompatible. System available RAM fraction is monitored.\nForked from default_gap_experiments.py SHA256 '+origin+'.')
old="""    rss = a.process_memory_mb or int((available - 2048) // 256) * 256
    memory = a.memory_mb or int(rss * .8 // 256) * 256
    if not 0 < memory < rss or rss + 2048 > available:
        raise ValueError(f'Invalid budget: SCIP={memory}, RSS={rss}, available={available:.0f} MiB')
"""
new="""    if not 0 < a.min_available_fraction < .5:
        raise ValueError('System available-RAM fraction must be between 0 and 0.5')
    # SCIP's native default is its unlimited-memory sentinel, not a RAM quota.
    # Retaining the numeric setting lets unchanged helpers use their existing API.
    from scip_imports import scip
    probe = scip.Model()
    try:
        memory = probe.getParam('limits/memory')
    finally:
        probe.freeProb()
    if memory < 1e12:
        raise RuntimeError('SCIP native memory default is unexpectedly capped')
"""
replace(old,new)
replace("cleanup_limit=a.stage2_limit, memory_mb=memory, process_memory_mb=rss,\n        reserve_mb=2048, available_at_prepare_mib=available, wall_limit=a.wall_limit,",
        "cleanup_limit=a.stage2_limit, memory_mb=memory, process_memory_mb=None,\n        memory_policy='scip_native_unlimited_system_available_fraction',\n        min_available_fraction=a.min_available_fraction,\n        available_at_prepare_mib=available, wall_limit=a.wall_limit,")
replace("    with output_lock(RESULTS / '.default_gap_queue'), output_lock(out):",
        "    with output_lock(RESULTS / '.default_gap_queue'), output_lock(out):")
replace("            if available < st['process_memory_mb'] + st['reserve_mb']:\n                raise RuntimeError(f'Need {st[\"process_memory_mb\"] + st[\"reserve_mb\"]} MiB; available {available:.0f}. Frozen budget retained; resume after freeing RAM.')",
        "            vm = psutil.virtual_memory()\n            if vm.available / vm.total < st['min_available_fraction']:\n                raise RuntimeError('Low system available RAM; no cell started. Resume after releasing RAM.')")
replace("            peak = last = 0", "            peak = last = 0\n            minimum_available_fraction = 1.0")
replace("                        if rss > st['process_memory_mb']:\n                            reason = 'process_memory_guard'",
        "                        vm = psutil.virtual_memory()\n                        fraction = vm.available / vm.total\n                        minimum_available_fraction = min(minimum_available_fraction, fraction)\n                        if fraction < st['min_available_fraction']:\n                            reason = 'system_available_memory_guard'")
replace("dict(exit_code=code, peak_rss_mib=peak, wall_seconds=durations[-1], log=str(logpath))",
        "dict(exit_code=code, peak_rss_mib=peak, wall_seconds=durations[-1], log=str(logpath),\n                memory_policy=st['memory_policy'], min_system_available_fraction=minimum_available_fraction)")
replace("    p.add_argument('--memory-mb', type=int, default=0)\n    p.add_argument('--process-memory-mb', type=int, default=0)",
        "    p.add_argument('--min-available-fraction', type=float, default=.10,\n                   help='System-wide available RAM safety threshold; no fixed solver or RSS cap')")
replace("'--memory-mb', '--process-memory-mb'", "'--min-available-fraction'")
replace("    spec = read(out / 'campaign.json')\n    if digest", "    spec = read(out / 'campaign.json')\n    if spec['settings'].get('memory_policy') != 'scip_native_unlimited_system_available_fraction':\n        raise RuntimeError('This entry only accepts new uncapped campaigns; old frozen runs stay unchanged')\n    if digest")
assert 'process_memory_guard' not in code
assert "process_memory_mb=None" in code
assert "rss >" not in code
if target.exists():raise FileExistsError(target)
target.write_text(code,encoding='utf-8')
print(target)
print('source_sha256',origin)
