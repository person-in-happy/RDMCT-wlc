"""Scheduler contract tests using simulated children; no optimization or model build."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import tempfile
import unittest

ENTRY = Path(__file__).with_name('queue.py')
spec = importlib.util.spec_from_file_location('thesis_queue', ENTRY)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

SETTINGS = dict(max_workers=4, min_available_gib=8., launch_available_gib=10.,
                min_commit_headroom_gib=8., launch_commit_headroom_gib=12.,
                reservation_gib_n4=3., reservation_gib_n6=5.,
                max_cpu_percent_to_launch=85., launch_spacing_seconds=.05,
                refresh_seconds=1., poll_seconds=.05)


class SchedulingContracts(unittest.TestCase):
    def test_unallocated_growth_cannot_be_double_spent(self):
        active = [dict(reservation_gib=5., rss_gib=1.)]
        self.assertEqual(q.admission(SETTINGS, active, 5., 18., 60., 10.), 'waiting_for_RAM')
        active[0]['rss_gib'] = 5.
        self.assertEqual(q.admission(SETTINGS, active, 5., 18., 60., 10.), 'ready')

    def test_cpu_commit_and_parallel_limits(self):
        self.assertEqual(q.admission(SETTINGS, [], 3., 30., 14., 10.), 'waiting_for_commit_headroom')
        self.assertEqual(q.admission(SETTINGS, [], 3., 30., 60., 90.), 'waiting_for_CPU')
        active = [dict(reservation_gib=3., rss_gib=3.)] * 4
        self.assertEqual(q.admission(SETTINGS, active, 3., 30., 60., 10.), 'parallel_limit')

    def test_external_paths_rejected(self):
        with self.assertRaises(ValueError):
            q.root_path(q.ROOT)
        with self.assertRaises(ValueError):
            q.root_path(q.RESULTS)

    def test_wait_then_four_independent_children_and_receipts(self):
        clock, launches = [0.], []
        with tempfile.TemporaryDirectory(prefix='queue_test_', dir=ENTRY.parent) as temp:
            out, stage = Path(temp), Path(temp) / 'chain'
            cells = [dict(id=f'cell{i}', case='n4_test', seed=i, arm='test') for i in range(4)]
            q.dump(stage / 'campaign.json', dict(cells=cells, settings=dict(time_limit=.5, wall_limit=2.)))

            class SimulatedChild:
                def __init__(self, args, **kwargs):
                    assert clock[0] >= .2, 'Child launched while predecessor active'
                    self.pid = 900000 + len(launches)
                    self.start = clock[0]
                    self.dest = stage / 'runs' / args[args.index('--cell')+1]
                    self.returncode = None
                    launches.append(self)
                def poll(self):
                    if self.returncode is None and clock[0]-self.start >= .5:
                        q.dump(self.dest / 'result.json', dict(solutions=0, test_fixture=True))
                        q.dump(self.dest / 'evidence.json', dict(valid=False, state='timelimit',
                               result_sha256=q.sha(self.dest / 'result.json')))
                        self.returncode = 0
                    return self.returncode
                def wait(self, timeout=None):
                    assert self.poll() is not None
                    return self.returncode
                def terminate(self):
                    self.returncode = -1

            def fake_gate(owned):
                return dict(allowed=clock[0] >= .2, foreign_pids=[1] if clock[0] < .2 else [], predecessor_locked=clock[0]<.2)

            def advance(seconds):
                clock[0] += seconds

            with patch.object(q.time,'monotonic',side_effect=lambda:clock[0]), \
                 patch.object(q.time,'sleep',side_effect=advance), \
                 patch.object(q,'gate',side_effect=fake_gate), \
                 patch.object(q,'predecessor_status',return_value=None), \
                 patch.object(q,'commit_free_gib',return_value=60.), \
                 patch.object(q.psutil,'virtual_memory',return_value=SimpleNamespace(available=30*q.GIB)), \
                 patch.object(q.psutil,'cpu_percent',return_value=10.), \
                 patch.object(q.subprocess,'Popen',side_effect=SimulatedChild):
                result = q.run_stage(out,'chain',dict(settings=SETTINGS))
            self.assertEqual(result,dict(expected=4, complete=4, failed=0, pending=0, valid=0))
            self.assertEqual(len(launches),4)
            records = [q.read(stage/'launch_records'/f'cell{i}.json') for i in range(4)]
            self.assertEqual(max(len(r['parallel_cells']) for r in records),4)
            for i in range(4):
                resource = q.read(stage/'runs'/f'cell{i}'/'resources.json')
                self.assertEqual(resource['exit_code'],0)
                self.assertFalse(resource['gpu'])
                self.assertEqual(resource['threads'],1)

    def test_chain_failure_blocks_conditional_rhythm(self):
        with tempfile.TemporaryDirectory(prefix='queue_test_',dir=ENTRY.parent) as temp:
            out = Path(temp)
            failed = dict(expected=24,complete=23,failed=1,pending=0,valid=0)
            with patch.object(q,'checked',return_value=dict(settings=SETTINGS)), \
                 patch.object(q,'run_stage',return_value=failed), \
                 patch.object(q,'child_action') as action:
                q.run(out)
            action.assert_not_called()
            self.assertFalse((out/'supervisor.lock').exists())
            self.assertEqual(q.read(out/'finished.json')['state'],'chain_finished_with_failures')


if __name__ == '__main__':
    unittest.main(verbosity=2)
