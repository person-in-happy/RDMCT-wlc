"""Bind reviewed PDF/source to checked results and package the Chinese revision."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json
import re
import zipfile
import pymupdf

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent
REVIEWED_PDF = '54d411e23639dae855326769af7bb850232ce8d4f7b1bd938f34dfff7856e008'


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def main():
    source, pdf = PAPER / 'JMS_Review_CN.tex', PAPER / 'JMS_Review_CN.pdf'
    text = source.read_text('utf-8')
    original = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
    result = read(HERE / 'verified_strengthening.json')
    build = read(PAPER / 'output/model4_cn_build/build_report.json')
    assert sha(source) == build['source_sha256']
    assert sha(pdf) == build['pdf_sha256'] == REVIEWED_PDF
    assert sha(PAPER / 'output/pdf/JMS_Review_CN.pdf') == REVIEWED_PDF
    assert result['completed'] == result['feasible'] == 48
    assert result['statuses'] == {'optimal': 12, 'timelimit': 36}
    assert all(r['independent_full_assignment_check'] for r in result['rows'])
    for path, expected in result['snapshots'].items():
        assert sha(Path(path)) == expected, path
    assert sha(PAPER / 'model4_pjob_fifo_20261029/model.py') == 'f3abcd2dbcc4a1d1afa93379261870f8e2f078ba145b1caa590282898d76722e'
    for name in ('undefined_references', 'overfull_boxes', 'duplicate_labels'):
        assert build[name] == 0
    keys = re.findall(r'\\bibitem\{([^}]+)\}', text)
    cites = [k.strip() for group in re.findall(r'\\cite[pt]?\{([^}]+)\}', text) for k in group.split(',')]
    assert len(keys) == 31 and set(keys) == set(cites)
    labels = re.findall(r'\\label\{([^}]+)\}', text)
    refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', text)
    assert len(labels) == len(set(labels)) and set(refs) <= set(labels)
    assert not any(term in text for term in ('匿名', '模型4', '模型2'))
    def equations(s):
        return {re.search(r'\\label\{([^}]+)\}', eq).group(1): eq
                for eq in re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}', s, re.S)}
    oldeq, neweq = equations(original), equations(text)
    assert len(neweq) == len(oldeq) == 39
    assert set(oldeq) == set(neweq)
    assert [k for k in oldeq if oldeq[k] != neweq[k]] == ['eq:operation-time-cn']
    assert neweq['eq:operation-time-cn'] == oldeq['eq:operation-time-cn'].replace(r'\le Mb_o', r'\le\overline T b_o')
    intro = lambda s: s.split(r'\section{引言}', 1)[1].split(r'\section{双源混流旋转腔组合设备调度模型}', 1)[0]
    assert intro(text) == intro(original)
    assert text.split(r'\section*{CRediT', 1)[1] == original.split(r'\section*{CRediT', 1)[1]
    assert text.split(r'\begin{abstract}', 1)[1].splitlines()[1] == original.split(r'\begin{abstract}', 1)[1].splitlines()[1]
    doc = pymupdf.open(pdf)
    assert len(doc) == 18
    assert all(p.get_text().strip() for p in doc)
    assert '615' in ''.join(p.get_text() for p in doc)
    assert '1440' in ''.join(p.get_text() for p in doc)
    (HERE / 'manuscript.patch').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), text.splitlines(True), fromfile='original/JMS_Review_CN.tex',
        tofile='JMS-version/JMS_Review_CN.tex')), 'utf-8')
    claims = dict(
        coverage=dict(original_completed=453, original_feasible=441, prior_supplement=114,
                      new_supplement=48, total_completed_records=615, total_feasible_records=603,
                      retained_execution_interruptions=3, records_are_not_independent_instances=True),
        pure_chain_cleaning=dict(n=24, threshold=5, source='dual', weights=[0, 5, 25, 100], seeds=[1, 2, 3],
            cmax=4785, waiting_before=3109, waiting_after=1440,
            waiting_reduction_percent=100 * (1 - 1440 / 3109), maximum_wait_before=437, maximum_wait_after=65,
            rhythm_before=696, rhythm_after=696, cleanings=2, optimality_scope='fixed_structure_refinement',
            original_variables=1080365, substituted_variables=3645, substituted_constraints=34538),
        representation=dict(cases=6, paired_seed_comparisons=18, runs=36,
            scope='membership representation with identical pair-slot routes and strict FIFO',
            preparation_reduction_percent=[9.256357, 14.980832], preparation_includes_start_checks=True,
            total_variable_reduction_percent=[0.010102, 0.224335],
            matrix_nonzero_reduction_percent=[0.053353, 12.812509],
            matched_product_cmax=True, all_returned_common_incumbent=True,
            solver_budget=300, actual_solver_seconds=[300, 392],
            algorithm_speedup_claim=False, universal_memory_reduction_claim=False),
        corrected_equation='eq:operation-time-cn: enabled start/end bounded by the configured horizon',
        evidence='verified_strengthening.json')
    dump(HERE / 'claim_evidence.json', claims)
    completion = dict(source_sha256=sha(source), pdf_sha256=sha(pdf), pages=len(doc),
        compilation_passes=3, undefined_references=0, overfull_boxes=0, duplicate_labels=0,
        bibliography_entries=31, all_references_cited=True, numbered_equations=39,
        preserved_equations=38, corrected_equations=['eq:operation-time-cn'],
        introduction_and_abstract_opening_preserved=True, declarations_and_references_preserved=True,
        full_assignment_replays=48, input_assignment_replays=9, wafer_projection_checks=18,
        prior_result_hashes_checked=result['prior_hashes_checked'], new_optimization_runs_started=0,
        original_results_and_frozen_backend_unchanged=True,
        visual_review_completed=True, overview_pages=list(range(1, 19)),
        enlarged_pages=[1, 6, 12, 13, 14, 15, 16, 17, 18],
        evidence_sha256=sha(HERE / 'verified_strengthening.json'), review_sha256=sha(HERE / 'REVIEW_CN.md'))
    dump(HERE / 'completion_review.json', completion)
    package = PAPER / 'output/JMS_CN_strengthening_review_20261101.zip'
    files = {source: 'JMS_Review_CN.tex', pdf: 'JMS_Review_CN.pdf'}
    for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text):
        candidates = [p for p in (PAPER / 'figures').rglob(name + '.*') if p.suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg', '.eps')]
        assert candidates, name
        for p in candidates:
            files[p] = p.relative_to(PAPER).as_posix()
    for name in ('REVIEW_CN.md', 'verified_strengthening.json', 'claim_evidence.json', 'completion_review.json',
                 'audit_strengthening.py', 'update_manuscript.py', 'finalize_review.py', 'manuscript.patch'):
        files[HERE / name] = 'review/' + name
    for name in ('verified_supplements.json', 'audit_supplements.py'):
        files[HERE.parent / '20261101_supplement_update' / name] = 'review/prior_supplement/' + name
    manifest = {target: sha(path) for path, target in files.items()}
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, target in files.items():
            z.write(path, target)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr('README.txt',
            'Chinese manuscript updated with 48 independently revalidated strengthening results.\n'
            'Compile JMS_Review_CN.tex using XeLaTeX (three passes); elsarticle and ctex are required.\n'
            'review/ contains the audit report, provenance, checked summaries and manuscript diff; it is separate from submission text.\n'
            'The original experiment assignments and frozen solvers remain in the research workspace.\n')
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(target)).hexdigest() == expected for target, expected in manifest.items())
    dump(HERE / 'package_receipt.json', dict(path=str(package), sha256=sha(package), bytes=package.stat().st_size,
                                            files=len(files), source_sha256=sha(source), pdf_sha256=sha(pdf)))
    print(json.dumps(dict(pages=len(doc), revalidated_results=48, source_sha256=sha(source),
                         pdf_sha256=sha(pdf), package=str(package), bytes=package.stat().st_size)))


if __name__ == '__main__':
    main()
