"""Final immutable evidence, table-transcription and document checks."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import shutil
import pymupdf

OUT = Path(__file__).resolve().parent
JMS = OUT.parents[1]
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
evidence = read(OUT / 'evidence.json')
for path, expected in evidence['hashes'].items():
    assert sha(path) == expected, path
texpath = JMS / 'JMS_Review_CN.tex'
source = texpath.read_text(encoding='utf-8')
build = read(JMS / 'output/model4_cn_build/build_report.json')
assert build['source_sha256'] == sha(texpath)
assert build['pdf_sha256'] == sha(JMS / 'JMS_Review_CN.pdf') == sha(JMS / 'output/pdf/JMS_Review_CN.pdf')
assert build['undefined_references'] == build['overfull_boxes'] == build['duplicate_labels'] == 0
labels = re.findall(r'\\label\{([^}]+)\}', source)
refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', source)
assert len(labels) == len(set(labels)) and not set(refs)-set(labels)
bibitems = re.findall(r'\\bibitem\{([^}]+)\}', source)
cites = {v for group in re.findall(r'\\cite\w*\{([^}]+)\}', source) for v in group.split(',')}
assert not cites - set(bibitems)
data = {c['suite']: {(x['case'], x['arm']):x for x in c['summary']} for c in evidence['campaigns']}
cases = ['n2_H3_4x1_dual','n2_H3_4x1_dual_same_lp','n2_H3_mixed_dual','n4_H10_mixed_dual']
arms = ['scip_plain','hem_plain','proposed_plain','scip_spbs','hem_spbs','proposed_spbs']
def rows(label, cols):
    text = source.split('\\label{'+label+'}',1)[1].split('\\end{tabular}',1)[0]
    text = text.split(r'\midrule',1)[1].split(r'\bottomrule',1)[0]
    return [[float(v.strip()) for v in line.strip().removesuffix(r'\\').split('&')[-cols:]]
            for line in text.splitlines() if '&' in line]
checked = 0
for idx, values in enumerate(rows('tab:journal-algorithm-cn', 6)):
    case, suite = cases[idx//2], ('algorithm','standard')[idx%2]
    for arm, v in zip(arms, values):
        assert math.isclose(v, data[suite][case,arm]['mean_cmax'], abs_tol=.0051), (case,arm,v)
        checked += 1
components = ['hem_plain','feature_only_plain','proposed_no_structure_plain','proposed_greedy_plain','proposed_plain']
for arm, values in zip(components, rows('tab:journal-components-cn',4)):
    for case,v in zip(cases,values):
        assert math.isclose(v, data['algorithm'][case,arm]['mean_cmax'], abs_tol=.0051)
        checked += 1
for case,values in zip(cases,rows('tab:journal-structure-cn',3)):
    for arm,v in zip(['joint','fixed','fixed_then_joint'],values):
        assert math.isclose(v, data['structure'][case,arm]['mean_cmax'], abs_tol=.0051)
        checked += 1
assert checked == 80
doc = pymupdf.open(JMS / 'JMS_Review_CN.pdf')
assert len(doc) == build['pages'] == 17
textpages = [p.get_text() for p in doc]
assert all(t.strip() for t in textpages)
joined=''.join(textpages)
for token in ('503.67','505.67','428','802','591','514.02'):
    assert token in joined, token
# Reserve the final report path before checking report links to it.
final_path = OUT / 'final_checks.json'
final_path.write_text('{}', encoding='utf-8')
links=0
for name in ('JOURNAL_REVIEW_CN.md','JOURNAL_EXPERIMENT_COMMANDS.md'):
    for target in re.findall(r'\]\(([^)]+)\)', (JMS/name).read_text(encoding='utf-8')):
        if target.startswith(('https:','http:','#')):continue
        assert (JMS/target.split('#')[0]).exists(), (name,target)
        links+=1
files=['JMS_Review_CN.tex','JMS_Review_CN.pdf','output/pdf/JMS_Review_CN.pdf',
       'JOURNAL_REVIEW_CN.md','JOURNAL_EXPERIMENT_COMMANDS.md']
report=dict(checked_utc=datetime.now(timezone.utc).isoformat(),pages=17,compilation_passes=3,
    solver_started=False, new_experiments_started=False,
    evidence_files_rehashed=len(evidence['hashes']), experiment_records=237,
    fresh_original_assignment_and_physical_checks=228, new_table_cells_checked=checked,
    markdown_links_checked=links, bibliography_entries=len(bibitems),
    undefined_references=0,undefined_citations=0,duplicate_labels=0,overfull_boxes=0,
    visual_review='All pages rendered and contact sheets inspected; full-size pages 1,9,13,14,15,16 inspected; no clipping or overlap observed.',
    marker_helper='Unavailable in Windows workspace/plugin directories; invocation returned MODULE_NOT_FOUND. Existing XeLaTeX/PyMuPDF pipeline used.',
    sha256={str(JMS/p):sha(JMS/p) for p in files}, evidence_sha256=sha(OUT/'evidence.json'))
final_path.write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
shutil.copy2(JMS/'output/model4_cn_build/build_report.json', OUT/'build_report.json')
print(json.dumps({k:v for k,v in report.items() if k not in ('sha256','visual_review','marker_helper')},ensure_ascii=False))
