"""Verify and package this revision without invoking optimization."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent
EXPERIMENT = PAPER / 'experiments/review_followup_20261102'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text('utf-8'))


old = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
new = (PAPER / 'JMS_Review_CN.tex').read_text('utf-8')
build = read_json(PAPER / 'output/model4_cn_build/build_report.json')
entry = read_json(EXPERIMENT / 'entry_validation.json')
diagnostics_path = PAPER / 'revisions/20261101_deep_review/diagnostics.json'
diagnostics = read_json(diagnostics_path)
assert digest(HERE / 'original/JMS_Review_CN.tex') == diagnostics['source_sha256']
assert digest(PAPER / 'JMS_Review_CN.tex') == build['source_sha256']
assert digest(PAPER / 'JMS_Review_CN.pdf') == build['pdf_sha256']
assert digest(PAPER / 'output/pdf/JMS_Review_CN.pdf') == build['pdf_sha256']
assert build['pages'] == 18 and build['compilation_passes'] == 3
assert all(build[k] == 0 for k in ('undefined_references', 'overfull_boxes', 'duplicate_labels'))
assert entry['passed'] == 17 and entry['failed'] == 0 and entry['optimization_calls'] == 0
for path, expected in entry['implementation_hashes'].items():
    assert digest(ROOT / path) == expected, path

assert old.split(r'\begin{abstract}')[0] == new.split(r'\begin{abstract}')[0]
abstract_old = old.split(r'\begin{abstract}')[1].split(r'\end{abstract}')[0].strip()
abstract_new = new.split(r'\begin{abstract}')[1].split(r'\end{abstract}')[0].strip()
assert abstract_old.splitlines()[0] == abstract_new.splitlines()[0]
intro_old = old.split(r'\section{引言}')[1].split(r'\section{')[0]
intro_new = new.split(r'\section{引言}')[1].split(r'\section{')[0]
assert intro_old.replace(
    'Sun等报告了不同腔室工艺时长的差异，并利用设备数据分析定位导致吞吐率损失的\n步骤',
    'Sun等介绍了智能设备数据分析工具在半导体制造质量、效率与生产率改进中的\n应用',
) == intro_new
equations = re.compile(r'\\begin\{equation\}(.*?)\\end\{equation\}', re.S)
assert equations.findall(old) == equations.findall(new)
assert len(equations.findall(new)) == 39
assert old.split(r'\begin{thebibliography}')[1] == new.split(r'\begin{thebibliography}')[1]
bibkeys = set(re.findall(r'\\bibitem\{([^}]+)\}', new))
cited = {key.strip() for block in re.findall(r'\\cite\w*\{([^}]+)\}', new) for key in block.split(',')}
assert len(bibkeys) == 31 and cited == bibkeys, (bibkeys - cited, cited - bibkeys)
assert not any(word in new for word in ('匿名', '模型4', '模型2', '9.26', '14.98', '97.54'))

expected_flows = {
    'n8_H3_mixed_single': (1014, 480, 3252, 3668, 5194, 5076, 2.27),
    'n8_H3_mixed_dual': (1330, 494, 1536, 1536, 3794, 2958, 22.03),
}
flow_checks = []
for case, expected in expected_flows.items():
    row = next(r for r in diagnostics['phase_changes'] if r['case'] == case)
    observed = tuple(round(row[phase][key]) for key in (
        'product_route_wait', 'product_chamber_sum', 'product_flow_sum'
    ) for phase in ('before', 'after')) + (round(row['flow_reduction_percent'], 2),)
    assert observed == expected, (case, observed, expected)
    assert row['n'] == 3
    flow_checks.append({'case': case, 'seeds': 3, 'values': observed})

report = {
    'source_sha256': digest(PAPER / 'JMS_Review_CN.tex'),
    'pdf_sha256': digest(PAPER / 'JMS_Review_CN.pdf'),
    'build': build,
    'visual_review': {
        'all_18_pages_overview_reviewed': True,
        'enlarged_pages_reviewed': [1, 14, 15, 16, 17],
        'observed_layout_defects': 0,
    },
    'protected_content': {
        'abstract_opening_unchanged': True,
        'introduction_only_citation_claim_correction': True,
        'numbered_equations_unchanged': 39,
        'bibliography_entries_unchanged_and_all_cited': 31,
        'author_frontmatter_unchanged': True,
    },
    'flow_table_checks': flow_checks,
    'evidence_source': str(diagnostics_path.relative_to(ROOT)),
    'evidence_source_sha256': digest(diagnostics_path),
    'entry_checks_passed': 17,
    'entry_checks_failed': 0,
    'entry_implementation_hashes_match': True,
    'frozen_backend_sha256': digest(PAPER / 'model4_pjob_fifo_20261029/model.py'),
    'new_optimization_experiments_started': False,
    'pending_suites': ['timing', 'parallel', 'exact', 'residency'],
    'scope': 'Prior result and full-assignment validation records retained; no new scientific results claimed.',
}
(HERE / 'completion_review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')

files = [PAPER / 'JMS_Review_CN.tex', PAPER / 'JMS_Review_CN.pdf']
graphics_dirs = [PAPER / p for p in (
    'figures/final_results_cn', 'figures/pjob_sequence_cn', 'figures/terminology_cn', 'figures'
)]
for name in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', new):
    matches = [folder / (name + '.pdf') for folder in graphics_dirs if (folder / (name + '.pdf')).exists()]
    assert matches, name
    files.append(matches[0])
files += [EXPERIMENT / name for name in (
    'COMMANDS_CN.md', 'run_followup.ps1', 'followup.py', 'followup_models.py',
    'verify_entries.py', 'entry_validation.json'
)]
files += [HERE / name for name in ('CHANGES_CN.md', 'manuscript.patch', 'completion_review.json')]
files += [PAPER / 'revisions/20261101_deep_review/REVIEW_CN.md']
target = PAPER / 'output/JMS_CN_review_corrections_20261102.zip'
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as package:
    for path in files:
        package.write(path, str(path.relative_to(ROOT)))
    package.writestr('README.txt', (
        'Chinese manuscript revision and review follow-up commands, 2026-11-02.\n'
        'Compile JMS-version/JMS_Review_CN.tex with XeLaTeX (three passes).\n'
        'Experiment entry files must be run within the original repository; frozen backend and source results are dependencies.\n'
        'No new optimization experiments were launched in this revision.\n'
        'See COMMANDS_CN.md for the four pending suites and recovery commands.\n'
    ))
    package.writestr('MANIFEST.sha256', ''.join(f'{digest(p)}  {p.relative_to(ROOT).as_posix()}\n' for p in files))
with zipfile.ZipFile(target) as package:
    assert package.testzip() is None
receipt = {'package': str(target), 'sha256': digest(target), 'files': len(files), 'verified': True}
(HERE / 'delivery_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', 'utf-8')
print(json.dumps({'verification': 'passed', 'entry_checks': 17, 'pages': 18, **receipt}, indent=2))
