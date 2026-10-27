"""Exercise actual solver artifacts, including rejection of altered evidence."""
from pathlib import Path
import json,shutil,tempfile,unittest
from verify_exact_optimality import verify,ROOT
from render_certified_exact_gantt import checked_data
from run_exact_paper_queue import next_step

BASE=ROOT/'JMS-version/results/optimality_work_20261022/pipeline_smoke_n2'


class ProofTests(unittest.TestCase):
    def test_actual_positive_chain(self):
        proof=verify(BASE/'search_response',BASE/'final_certificate/certificate.json')
        self.assertTrue(proof['original_objective_globally_optimal']);self.assertEqual(proof['cmax'],324)
        data,_=checked_data(BASE/'proof.json');self.assertEqual(data['cmax'],324)

    def test_altered_response_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'search';shutil.copytree(BASE/'search_response',path)
            with (path/'response.pb').open('ab') as stream:stream.write(b'tampered')
            with self.assertRaisesRegex(ValueError,'artifact hash'):verify(path,BASE/'final_certificate/certificate.json')

    def test_feasible_status_cannot_pass_as_optimal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'search';shutil.copytree(BASE/'search_response',path)
            result=json.loads((path/'result.json').read_text(encoding='utf-8-sig'));result['primary_status']='timelimit'
            (path/'result.json').write_text(json.dumps(result),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'not optimal'):verify(path,BASE/'final_certificate/certificate.json')

    def test_open_bound_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'search';shutil.copytree(BASE/'search_response',path)
            result=json.loads((path/'result.json').read_text(encoding='utf-8-sig'));result['primary_bound']=323
            (path/'result.json').write_text(json.dumps(result),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'bounds not closed'):verify(path,BASE/'final_certificate/certificate.json')

    def test_queue_never_skips_original_certification(self):
        self.assertEqual(next_step('search',0,BASE/'search_response'),'certify')
        self.assertEqual(next_step('certify',0,BASE/'final_certificate'),'verify')
        self.assertEqual(next_step('verify',0,BASE/'proof.json'),'render')
        self.assertEqual(next_step('search',1,BASE/'search_response'),'needs_review')
        self.assertEqual(next_step('search',0,BASE/'nonexistent'),'needs_review')


if __name__=='__main__':unittest.main()
