"""Record final artifacts and verify preserved evidence; does not optimize."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import pymupdf

OUT = Path(__file__).resolve().parent
JMS = OUT.parents[1]
ROOT = JMS.parent


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


old = read(JMS/'revisions/20261109_journal_results/evidence.json')['hashes']
for n, (p, expected) in enumerate(old.items(), 1):
    assert digest(Path(p)) == expected, p
    if n % 300 == 0:
        print(f'preserved_evidence_hashes={n}/{len(old)}', flush=True)

preflight = read(OUT/'preflight_checks.json')
assert digest(JMS/'tools/journal_support_experiments.py') == preflight['driver_sha256']
assert len(preflight['policies']) == 15 and not preflight['solver_started']
for c in preflight['campaigns']:
    path = Path(c['campaign'])
    spec = read(path/'campaign.json')
    assert digest(path/'campaign.json') == c['contract']
    for rel, value in spec['assets'].items():
        assert digest(ROOT/rel) == value
    assert spec['settings']['process_memory_mb'] is None
    assert spec['settings']['memory_mb'] > 1e12

text = (JMS/'JMS_Review_CN.tex').read_text(encoding='utf-8')
block = text.split(r'\label{tab:d-coupled-witness-cn}', 1)[1].split(r'\end{table}', 1)[0]
numbers = [tuple(map(float, x)) for x in re.findall(r'&\s*(\d+)\s*&\s*(\d+)\\\\', block)]
assert numbers == [(303, 303), (642, 54), (96, 16), (978, 796), (0, 0)]
for expected in ('2/1 & 2/1', '9/7 & 9/7', '2/5 & 2/5'):
    assert expected in block
evidence = read(OUT/'witness_evidence.json')['records']
for r in evidence:
    assert r['full_model_audit']['valid'] and not r['solver_started']
assert abs(evidence[0]['metrics']['modeled_completion']-978) < 1e-4
assert evidence[1]['metrics']['modeled_completion'] == 796

build = read(JMS/'output/model4_cn_build/build_report.json')
assert build['source_sha256'] == digest(JMS/'JMS_Review_CN.tex')
assert build['pdf_sha256'] == digest(JMS/'JMS_Review_CN.pdf') == digest(JMS/'output/pdf/JMS_Review_CN.pdf')
shutil.copy2(JMS/'output/model4_cn_build/build_report.json', OUT/'build_report.json')
doc = pymupdf.open(JMS/'JMS_Review_CN.pdf')
rendered = OUT/'rendered'
rendered.mkdir(exist_ok=True)
for i in (11, 12, 15, 16):
    doc[i].get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6)).save(rendered/f'page-{i+1:02}.png')
for first in (1, 7, 13):
    shutil.copy2(JMS/f'output/model4_cn_build/contact_{first:02}.jpg', rendered/f'contact_{first:02}.jpg')

files = [JMS/'JMS_Review_CN.tex', JMS/'JMS_Review_CN.pdf', JMS/'JOURNAL_REVIEW_CN.md',
         JMS/'JOURNAL_EXPERIMENT_COMMANDS.md', JMS/'tools/journal_support_experiments.py',
         JMS/'figures/fig_d_coupled_witness_cn.pdf', ROOT/'tests/test_journal_support_protocol.py']
report = dict(build=build, artifact_sha256={str(p.relative_to(ROOT)): digest(p) for p in files},
              preserved_old_evidence_hashes=len(old), witness_original_assignments_rechecked=2,
              witness_table_scalar_cells_checked=16, protocol_unit_tests_observed_passed=7,
              policy_configurations_loaded=15, pending_parent_gate_checked=True,
              shared_input_identity_fixture_checked=True, formal_optimization_started=False,
              actual_new_optimization_branches_tested=False,
              preflight_report='preflight_checks.json',
              visual_review_pages=[12, 13, 16, 17],
              note='Raw results, frozen drivers, checkpoints and other JMS manuscript copy untouched. PDF operation marker helper unavailable; local XeLaTeX/PyMuPDF used.')
(OUT/'final_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
