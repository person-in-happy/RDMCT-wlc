from pathlib import Path
from unittest.mock import patch
import importlib.util
import json
import tempfile
import unittest

ENTRY = Path(__file__).with_name('resume.py')
spec = importlib.util.spec_from_file_location('safe_resume', ENTRY)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data),encoding='utf-8')


class ResumeTests(unittest.TestCase):
    def test_completed_retained_interrupted_and_dependencies_selected(self):
        with tempfile.TemporaryDirectory(dir=ENTRY.parent,prefix='resume_test_') as tmp:
            out=Path(tmp)
            cells=[dict(id='done'),dict(id='prep'),dict(id='dependent',preparation='prep'),dict(id='ram_fail')]
            write(out/'runs/done/evidence.json',dict(valid=True))
            write(out/'runs/prep/failure.json',dict(reason='foreground_supervisor_interrupted'))
            write(out/'runs/dependent/failure.json',dict(reason='shared_preparation_failed'))
            write(out/'runs/ram_fail/failure.json',dict(reason='new_worker_RAM_guard'))
            state=r.analyze(out,dict(cells=cells))
            self.assertEqual(state['completed'],1)
            self.assertEqual({x['id'] for x in state['interrupted']},{'prep','dependent'})
            self.assertEqual([x['id'] for x in state['retained_failures']],['ram_fail'])

    def test_archive_preserves_contents_logs_and_completed_result(self):
        with tempfile.TemporaryDirectory(dir=ENTRY.parent,prefix='resume_test_') as tmp:
            out=Path(tmp)
            write(out/'runs/done/evidence.json',dict(valid=True))
            write(out/'runs/partial/trace.json',dict(test_only=True,progress=12))
            write(out/'logs/partial.log',dict(log='old attempt'))
            write(out/'launch_records/partial.json',dict(pid=999999))
            (out/'supervisor.lock').write_text('999999')
            state=r.analyze(out,dict(cells=[dict(id='done'),dict(id='partial')]))
            state.update(active_processes=[],lock_pid_alive=False)
            old=r.sha(out/'runs/partial/trace.json')
            done=r.sha(out/'runs/done/evidence.json')
            with patch.object(r,'active_processes',return_value=[]):
                archive=r.archive_interrupted(out,state)
            self.assertEqual(r.sha(archive/'runs/partial/trace.json'),old)
            self.assertEqual(r.sha(out/'runs/done/evidence.json'),done)
            self.assertFalse((out/'runs/partial').exists())
            self.assertTrue((archive/'logs/partial.log').exists())
            self.assertTrue((archive/'supervisor.lock').exists())
            self.assertTrue((archive/'resume_manifest.json').exists())

    def test_active_worker_prevents_mutation(self):
        with tempfile.TemporaryDirectory(dir=ENTRY.parent,prefix='resume_test_') as tmp:
            out=Path(tmp)
            write(out/'runs/partial/trace.json',dict(progress=12))
            state=dict(active_processes=[dict(pid=1)],lock_pid_alive=True,ambiguous=[])
            with self.assertRaises(RuntimeError):
                r.archive_interrupted(out,state)
            self.assertTrue((out/'runs/partial/trace.json').exists())
            self.assertFalse((out/'interrupted_attempts').exists())

    def test_ambiguous_result_not_retried(self):
        with tempfile.TemporaryDirectory(dir=ENTRY.parent,prefix='resume_test_') as tmp:
            out=Path(tmp)
            write(out/'runs/one/evidence.json',dict(valid=True))
            write(out/'runs/one/failure.json',dict(reason='foreground_supervisor_interrupted'))
            state=r.analyze(out,dict(cells=[dict(id='one')]))
            state.update(active_processes=[],lock_pid_alive=False)
            with patch.object(r,'active_processes',return_value=[]):
                with self.assertRaises(RuntimeError):
                    r.archive_interrupted(out,state)
            self.assertFalse((out/'interrupted_attempts').exists())

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            r.safe_path(r.CAMPAIGN,'../another_campaign')


if __name__=='__main__':
    unittest.main(verbosity=2)
