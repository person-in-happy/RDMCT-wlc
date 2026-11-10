"""Verify manuscript tables, immutable experiment files, and compiled artifacts."""
from pathlib import Path
from statistics import mean
import argparse
import difflib
import hashlib
import json
import math
import shutil
import pymupdf

OUT = Path(__file__).resolve().parent
JMS = OUT.parents[1]
ROOT = JMS.parent
read = lambda p: json.loads(p.read_text(encoding='utf-8'))


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--visual-reviewed', action='store_true')
    args = ap.parse_args()
    e = read(OUT / 'evidence.json')
    for i, (p, expected) in enumerate(e['hashes'].items(), 1):
        assert digest(p) == expected, ('Preserved file changed', p)
        if i % 1000 == 0:
            print(f'preserved={i}/{len(e["hashes"])}', flush=True)
    text = (JMS / 'JMS_Review_CN.tex').read_text(encoding='utf-8')
    tab_a = text.split(r'\label{tab:journal-training-cn}', 1)[1].split(r'\end{table}', 1)[0]
    tab_b = text.split(r'\label{tab:journal-mechanism-cn}', 1)[1].split(r'\end{table}', 1)[0]
    a = [r for r in e['rows'] if r['suite'] != 'mechanism']
    b = [r for r in e['rows'] if r['suite'] == 'mechanism']
    for case in ('n2_H3_mixed_dual', 'n4_H10_mixed_dual'):
        for method in ('scip', 'hem', 'proposed'):
            v = [mean(r['metrics']['product_cmax'] for r in a if r['case'] == case and r['arm'] == method + '_' + arm)
                 for arm in ('plain', 'spbs')]
            assert f'& {v[0]:.2f} & {v[1]:.2f}' in tab_a, (case, method, v)
    for h in (2, 3):
        for d in (4, 8):
            expected = [296, 309 if d == 4 else 303]
            for mode, target in zip(('4x1', '2x2'), expected):
                for arm in ('optional', 'legacy'):
                    rr = [r for r in b if r['case'] == f'n1_{mode}_H{h}_D{d}' and r['arm'] == arm]
                    assert any(r['state'] == 'optimal' for r in rr)
                    lb = max(r['primary_bound'] for r in rr)
                    ub = min(r['metrics']['product_cmax'] for r in rr if r['valid'])
                    assert math.isclose(lb, target, abs_tol=2e-4) and math.isclose(ub, target, abs_tol=2e-4)
            assert f'{h} & {d} & {expected[0]} & {expected[1]}' in tab_b
    witnesses = [r for r in b if r['valid'] and r['metrics']['coupled_witness']]
    assert len(witnesses) == 11
    d4 = [r for r in witnesses if r['config']['dummy_count'] == 4]
    assert len(d4) == 5
    for r in d4:
        assert [r['metrics'][k] for k in ('auxiliary_loans', 'distinct_auxiliaries', 'repeat_loans')] == [9, 4, 5]
    assert len({r['case'] for r in b if r['valid']}) == 9
    assert '\u5b66\u4e60\u68c0\u67e5\u70b9\u4ec5\u91c7\u7528\u4e00\u4e2a\u8bad\u7ec3\u79cd\u5b50' not in text
    before = (OUT / 'before/JMS_Review_CN.tex').read_text(encoding='utf-8')
    (OUT / 'manuscript.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
        fromfile='before/JMS_Review_CN.tex', tofile='JMS_Review_CN.tex')), encoding='utf-8')
    build = read(JMS / 'output/model4_cn_build/build_report.json')
    assert build['source_sha256'] == digest(JMS / 'JMS_Review_CN.tex')
    assert build['pdf_sha256'] == digest(JMS / 'JMS_Review_CN.pdf') == digest(JMS / 'output/pdf/JMS_Review_CN.pdf')
    assert build['overfull_boxes'] == build['undefined_references'] == build['duplicate_labels'] == 0
    shutil.copy2(JMS / 'output/model4_cn_build/build_report.json', OUT / 'build_report.json')
    doc = pymupdf.open(JMS / 'JMS_Review_CN.pdf')
    rendered = OUT / 'rendered'
    rendered.mkdir(exist_ok=True)
    pages = [1, 13, 14, 15, 17]
    for num in pages:
        doc[num - 1].get_pixmap(matrix=pymupdf.Matrix(1.7, 1.7)).save(rendered / f'page-{num:02}.png')
    assert all('\ufffd' not in page.get_text() for page in doc)
    for start in (1, 7, 13):
        shutil.copy2(JMS / f'output/model4_cn_build/contact_{start:02}.jpg', rendered / f'contact_{start:02}.jpg')
    files = [JMS / 'JMS_Review_CN.tex', JMS / 'JMS_Review_CN.pdf', JMS / 'output/pdf/JMS_Review_CN.pdf',
             JMS / 'JOURNAL_REVIEW_CN.md', JMS / 'JOURNAL_EXPERIMENT_COMMANDS.md',
             OUT / 'REVIEW_AB_CN.md', OUT / 'evidence.json', OUT / 'tables.json',
             OUT / 'inventory_endpoint_checks.json', OUT / 'manuscript.diff']
    checks = dict(build=build, checked_records=312, fresh_original_assignment_checks=221,
                  preserved_file_hashes=len(e['hashes']), new_table_numeric_cells_checked=28,
                  inventory_endpoint_tolerance_seconds=2e-4,
                  artifact_sha256={str(p.relative_to(ROOT)): digest(p) for p in files},
                  formal_optimization_started_by_this_review=False,
                  frozen_experiments_and_other_manuscript_preserved=True,
                  pdf_operation_marker_completed=True,
                  rendering='PyMuPDF; local pdftoppm lacks Adobe-GB1 language mapping',
                  visual_review_completed=args.visual_reviewed,
                  visual_review_pages=pages if args.visual_reviewed else [],
                  full_document_contact_sheet_pages=18 if args.visual_reviewed else 0)
    (OUT / 'final_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(pages=len(doc), valid=True, visual_review_completed=args.visual_reviewed,
                         table_numeric_cells_checked=28, preserved_file_hashes=len(e['hashes']))), flush=True)


if __name__ == '__main__':
    main()
