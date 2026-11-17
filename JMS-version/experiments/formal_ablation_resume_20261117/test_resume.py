"""Interruption/recovery tests use isolated fixtures, never the running campaign."""
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import resume as r


class ResumeTests(unittest.TestCase):
    def setUp(self):
        root = (r.f.JMS / 'results').resolve()
        self.temp = tempfile.TemporaryDirectory(prefix='resume_fixture_', dir=root)
        self.out = Path(self.temp.name).resolve()
        self.assertTrue(self.out.is_relative_to(root))
        self.spec = {'cells': [{'id': 'done'}, {'id': 'prep'}, {'id': 'dependent', 'preparation': 'prep'},
                               {'id': 'partial'}, {'id': 'real_error'}]}

    def tearDown(self):
        # Resolve and verify the automatically generated workspace test directory before recursive cleanup.
        self.assertTrue(self.out.is_relative_to((r.f.JMS / 'results').resolve()))
        self.assertTrue(self.out.name.startswith('resume_fixture_'))
        self.temp.cleanup()

    def write(self, relative, data):
        r.f.dump(self.out / relative, data)

    def complete(self, name):
        directory = self.out / 'runs' / name
        self.write(f'runs/{name}/result.json', {'original_model_check': True, 'validation': {'valid': True}})
        self.write(f'runs/{name}/variables.json', {'values': {'Cmax': 500}})
        self.write(f'runs/{name}/trace.json', [{'allocated_budget_time': 10, 'cmax': 500}])
        evidence = dict(valid=True, budget_eligible=True, resource_interruption=False,
                        result_sha256=r.f.sha(directory / 'result.json'),
                        assignment_sha256=r.f.sha(directory / 'variables.json'))
        self.write(f'runs/{name}/evidence.json', evidence)
        return r.f.sha(directory / 'evidence.json')

    def test_complete_retained_and_partial_attempt_archived_intact(self):
        digest = self.complete('done')
        self.write('runs/partial/input.json', {'source': 'original'})
        self.write('runs/partial/trace.json', [{'interrupted_incumbent': 400}])
        self.write('launch_records/partial.json', {'pid': 123})
        (self.out / 'logs').mkdir()
        (self.out / 'logs/partial.log').write_text('partial raw log', encoding='utf-8')
        plan = r.plan_resume(self.out, self.spec)
        self.assertEqual(plan['completed'], ['done'])
        self.assertEqual(plan['actions'][0]['kind'], 'restart_incomplete')
        archive = self.out / 'continuations/test'
        r.apply_plan(self.out, archive, plan)
        self.assertEqual(r.f.sha(self.out / 'runs/done/evidence.json'), digest)
        self.assertFalse((self.out / 'runs/partial').exists())
        self.assertEqual(r.f.read(archive / 'attempts/partial/trace.json'), [{'interrupted_incumbent': 400}])
        self.assertEqual((archive / 'logs/partial.log').read_text(encoding='utf-8'), 'partial raw log')
        self.assertTrue((archive / 'launch_records/partial.json').exists())

    def test_interrupted_preparation_restores_dependents_but_retains_real_error(self):
        self.write('runs/prep/failure.json', {'reason': 'RAM_guard'})
        self.write('runs/dependent/failure.json', {'reason': 'shared_preparation_failed'})
        self.write('runs/real_error/failure.json', {'reason': 'worker_exit', 'exit_code': 1})
        plan = r.plan_resume(self.out, self.spec)
        self.assertEqual({a['id'] for a in plan['actions']}, {'prep', 'dependent'})
        self.assertEqual(plan['retained_failures'], [{'id': 'real_error', 'reason': 'worker_exit'}])

    def test_completed_certificate_survives_late_interruption_marker(self):
        digest = self.complete('done')
        self.write('runs/done/failure.json', {'reason': 'foreground_supervisor_interrupted'})
        plan = r.plan_resume(self.out, self.spec)
        self.assertEqual(plan['actions'][0]['kind'], 'recover_completed')
        archive = self.out / 'continuations/test'
        r.apply_plan(self.out, archive, plan)
        self.assertEqual(r.f.sha(self.out / 'runs/done/evidence.json'), digest)
        self.assertFalse((self.out / 'runs/done/failure.json').exists())
        self.assertTrue((archive / 'completed_failure_markers/done.json').exists())

    def test_resource_interruption_with_partial_certificate_is_retried(self):
        self.complete('prep')
        evidence = r.f.read(self.out / 'runs/prep/evidence.json')
        evidence.update(resource_interruption=True, budget_eligible=False)
        self.write('runs/prep/evidence.json', evidence)
        self.write('runs/dependent/failure.json', {'reason': 'shared_preparation_ineligible'})
        plan = r.plan_resume(self.out, self.spec)
        self.assertEqual({a['id'] for a in plan['actions']}, {'prep', 'dependent'})

    def test_active_campaign_does_not_create_duplicate_or_touch_output(self):
        digest = self.complete('done')
        with patch.object(r.f, 'checked', return_value=self.spec), \
             patch.object(r, 'active_processes', return_value=[{'pid': 999, 'role': 'run'}]), \
             patch.object(r, 'make_archive') as archive, contextlib.redirect_stdout(io.StringIO()):
            r.resume(self.out)
            archive.assert_not_called()
        self.assertEqual(r.f.sha(self.out / 'runs/done/evidence.json'), digest)

    def test_resume_pipeline_releases_stale_locks_and_calls_original_supervisor(self):
        self.complete('done')
        self.write('campaign.json', self.spec)
        self.write('runs/partial/input.json', {'source': 'original'})
        (self.out / 'supervisor.lock').write_text('999999999')
        (self.out / 'resume.guard.json').write_text('')
        with patch.object(r.f, 'checked', return_value=self.spec), \
             patch.object(r, 'active_processes', return_value=[]), \
             patch.object(r.f, 'report', return_value={'pending': 4}), \
             patch.object(r.f, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            r.resume(self.out)
            run.assert_called_once_with(self.out)
        self.assertFalse((self.out / 'supervisor.lock').exists())
        self.assertFalse((self.out / 'resume.guard.json').exists())
        self.assertTrue((self.out / 'runs/done/evidence.json').exists())
        self.assertFalse((self.out / 'runs/partial').exists())
        archives = list((self.out / 'continuations').iterdir())
        self.assertEqual(len(archives), 1)
        self.assertTrue((archives[0] / 'attempts/partial/input.json').exists())
        self.assertTrue((archives[0] / 'resume_plan.json').exists())

    def test_archive_refuses_paths_outside_campaign(self):
        outside = self.out.parent / 'outside_forbidden'
        with self.assertRaises(ValueError):
            r.safe_move(outside, self.out / 'continuations/bad', self.out)


if __name__ == '__main__':
    unittest.main()
