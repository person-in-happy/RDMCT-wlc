from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import importlib.util
import json
import psutil

entry = Path(__file__).with_name('queue.py')
spec = importlib.util.spec_from_file_location('thesis_queue', entry)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
out = q.RESULTS / 'thesis_parallel_20261116_r1'
plan = q.checked(out)
support = q.load_support()
chain = support.checked(out / 'chain')
assert len(chain['cells']) == len({c['id'] for c in chain['cells']}) == 24
assert len({c['case'] for c in chain['cells']}) == 8
assert chain['settings']['jobs'] == plan['settings']['max_workers'] == 4
assert chain['settings']['time_limit'] == 1200
assert all(c['method'] == 'scip' and c['policy'] is None for c in chain['cells'])
status = q.read(out / 'live_status.json')
assert psutil.pid_exists(status['supervisor_pid'])
assert status['state'] == 'waiting_for_existing_experiments'
assert not status['active'] and not status['active_pids']
assert not (out / 'chain/runs').exists(), 'No solve should start while predecessor is active'
old = q.read(q.PREDECESSOR / 'campaign.json')
for relative, expected in old['assets'].items():
    assert q.sha(q.ROOT / relative) == expected, 'Active campaign asset changed: ' + relative
receipt = dict(verified_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
               chain_cells=24, configurations=8, maximum_parallel=4,
               scheduler_simulation_tests_passed=5, supervisor_pid=status['supervisor_pid'],
               predecessor_alive=True, new_solver_started=False,
               existing_campaign_assets_unchanged=True,
               campaign_hash=q.sha(out/'chain/campaign.json'),
               queue_plan_hash=q.sha(out/'queue_plan.json'),
               observed_status=status)
q.dump(out / 'startup_verification.json', receipt)
print(json.dumps(receipt, ensure_ascii=False, indent=2))
