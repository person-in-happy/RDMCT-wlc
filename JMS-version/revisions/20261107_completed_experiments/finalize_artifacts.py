import json
import re
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone
import pymupdf

root = Path(__file__).resolve().parents[2]
p = Path(__file__).resolve().parent
s = (root / 'JMS_Review_CN.tex').read_text('utf-8')
log = (p / 'JMS_Review_CN.log').read_text('utf-8', errors='replace')
labels = re.findall(r'\\label\{([^}]+)\}', s)
refs = re.findall(r'\\(?:eqref|ref)\{([^}]+)\}', s)
bibs = set(re.findall(r'\\bibitem\{([^}]+)\}', s))
cites = [v.strip() for group in re.findall(r'\\cite\w*(?:\[[^\]]*\])*\{([^}]+)\}', s) for v in group.split(',')]
checks = {
    'checked_utc': datetime.now(timezone.utc).isoformat(),
    'source': 'JMS-version/JMS_Review_CN.tex',
    'undefined_references': sorted(set(refs) - set(labels)),
    'duplicate_labels': sorted({v for v in labels if labels.count(v) > 1}),
    'undefined_citations': sorted(set(cites) - bibs),
    'overfull_boxes': len(re.findall('Overfull', log)),
    'unresolved_latex_warnings': re.findall(r'^.*(?:undefined|Label\(s\) may have changed|Rerun to get).*$', log, re.M),
    'retained_warnings': ['Legacy fixltx2e package notice', 'hyperref drops author-footnote macros from PDF metadata', 'Underfull text lines; no overfull boxes'],
    'solver_experiments_started': False,
}
assert labels and cites
assert not any(checks[k] for k in ('undefined_references', 'duplicate_labels', 'undefined_citations', 'overfull_boxes', 'unresolved_latex_warnings')), checks
doc = pymupdf.open(p / 'JMS_Review_CN.pdf')
checks['pdf_pages'] = len(doc)
checks['page_text_characters'] = [len(page.get_text()) for page in doc]
assert min(checks['page_text_characters']) > 100
rendered = p / 'rendered'
rendered.mkdir(exist_ok=True)
for i, page in enumerate(doc):
    page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(rendered / f'page-{i+1:02d}.png')
checks['audits'] = {}
for name in ('current_evidence', 'extended_evidence'):
    data = json.loads((p / (name + '.json')).read_text('utf-8'))
    checks['audits'][name] = {
        'hash_errors': sum(len(c['hash_errors']) for c in data['campaigns']),
        'replay_valid_records': sum(c['counts']['replay_valid'] for c in data['campaigns']),
    }
    assert checks['audits'][name]['hash_errors'] == 0
out = root / 'output/pdf'
out.mkdir(parents=True, exist_ok=True)
shutil.copy2(p / 'JMS_Review_CN.pdf', root / 'JMS_Review_CN.pdf')
shutil.copy2(p / 'JMS_Review_CN.pdf', out / 'JMS_Review_CN.pdf')
checks['sha256'] = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (
    root / 'JMS_Review_CN.tex', root / 'JMS_Review_CN.pdf', out / 'JMS_Review_CN.pdf',
    p / 'REVIEW_CN.md', p / 'current_evidence.json', p / 'extended_evidence.json')}
(p / 'final_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps({k: checks[k] for k in ('pdf_pages', 'undefined_references', 'undefined_citations', 'overfull_boxes', 'audits')}, ensure_ascii=False))
