"""Verify the reviewed artifact, save evidence links, and package Chinese source."""
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
REVIEWED_PDF = 'f9b9652aae26e5d77b94653598e0209cdebe406c09224f3527d7b1160d2dd6f5'


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def main():
    src = PAPER / 'JMS_Review_CN.tex'
    pdf = PAPER / 'JMS_Review_CN.pdf'
    text = src.read_text('utf-8')
    original = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
    data = read(HERE / 'verified_supplements.json')
    build = read(PAPER / 'output/model4_cn_build/build_report.json')
    assert sha(src) == build['source_sha256']
    assert sha(pdf) == build['pdf_sha256'] == REVIEWED_PDF
    assert sha(PAPER / 'output/pdf/JMS_Review_CN.pdf') == REVIEWED_PDF
    assert data['completed'] == data['feasible'] == data['original_assignment_replays'] == 114
    assert all(r['independent_assignment_check'] for r in data['rows'])
    assert data['extra_hybrid_start_replays'] == 12
    source_hashes = {}
    for row in data['rows']:
        folder = PAPER / 'results' / row['campaign'] / 'runs' / row['id']
        for name, expected in row['hashes'].items():
            path = folder / name
            assert sha(path) == expected
            source_hashes[str(path.relative_to(ROOT))] = expected
        assert sha(Path(row['assignment'])) == row['assignment_sha256']
    assert len(source_hashes) == 342
    equations = lambda s: re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}', s, re.S)
    original_equations = equations(original)
    final_equations = equations(text)
    assert len(original_equations) == 38 and len(final_equations) == 39
    assert [e for e in final_equations if r'\label{eq:output-completion-cn}' not in e] == original_equations
    assert text.split(r'\section*{CRediT', 1)[1] == original.split(r'\section*{CRediT', 1)[1]
    keys = re.findall(r'\\bibitem\{([^}]+)\}', text)
    cites = [k.strip() for group in re.findall(r'\\cite[pt]?\{([^}]+)\}', text) for k in group.split(',')]
    assert len(keys) == 31 and set(keys) == set(cites)
    labels = re.findall(r'\\label\{([^}]+)\}', text)
    refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', text)
    assert len(labels) == len(set(labels)) and set(refs) <= set(labels)
    assert all(s not in text for s in ('匿名', '模型4', '模型2'))
    assert build['undefined_references'] == build['overfull_boxes'] == build['duplicate_labels'] == 0
    pdfdoc = pymupdf.open(pdf)
    assert len(pdfdoc) == 17
    assert any('References' in p.get_text() for p in pdfdoc)
    assert sha(PAPER / 'model4_pjob_fifo_20261029/model.py') == 'f3abcd2dbcc4a1d1afa93379261870f8e2f078ba145b1caa590282898d76722e'

    groups = {(g['suite'], g['case'], g['arm'], g['weight']): g for g in data['groups']}
    reductions = []
    for n,h in ((4,3),(4,10),(8,3),(8,10)):
        key = f'n{n}_H{h}_mixed_dual'
        joint = groups['baseline',key,'joint',None]['metrics']['product_cmax']
        fixed = groups['baseline',key,'fixed',None]['metrics']['product_cmax']
        reductions.append(100*(joint-fixed)/joint)
    assert round(min(reductions),2) == 5.20 and round(max(reductions),2) == 36.76
    longchain = groups['rhythm','n16_H10_2x2_dual','refinement',25]
    assert round(longchain['metrics']['rhythm_deviation']) == 784
    assert round(longchain['initial']['rhythm_deviation']) == 792
    mixture = groups['rhythm','n24_H5_mixed_dual','refinement',25]
    mixed_reduction = 100*(1-mixture['metrics']['route_wait_sum']/mixture['initial']['route_wait_sum'])
    assert round(mixed_reduction,2) == 61.55
    memory = [r for r in data['rows'] if r['suite']=='rhythm' and r['state']=='memlimit']
    assert len(memory) == 12
    assert all(r['case']=='n24_H5_2x2_dual' for r in memory)
    hybrid = [r for r in data['rows'] if r['arm']=='fixed_then_joint']
    assert len(hybrid) == 12 and all(abs(r['metrics']['product_cmax']-r['hybrid_pre_cmax'])<2e-4 for r in hybrid)
    assert data['cleanup_improved'] == 16 and data['cleanup_cmax_improved'] == 1
    (HERE / 'manuscript.patch').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), text.splitlines(True), fromfile='original/JMS_Review_CN.tex',
        tofile='JMS-version/JMS_Review_CN.tex')), 'utf-8')
    applied = text.split(r'\section{计算实验与结果分析}',1)[1].split(r'\section*{CRediT',1)[0]
    (HERE / 'applied_experiment_section.tex').write_text(r'\section{计算实验与结果分析}'+applied, 'utf-8')
    claims = dict(
        coverage={'main_completed':453,'main_feasible':441,'supplement_records':114,
                  'total_completed_records':567,'total_feasible_records':555,
                  'records_are_not_independent_instances':True},
        fixed_vs_joint_case_mean_reduction_percent=reductions,
        longchain_rhythm={'before':792,'after':784,'product_cmax':2537},
        mixed_cleaning_wait={'before':3745,'after':1440,'reduction_percent':mixed_reduction,
                             'rhythm_unchanged':20,'cleanings':2},
        cleanup={'records':42,'completion_improved':16,'primary_improved':1,
                 'all_primary_and_secondary_caps_preserved':True},
        still_open=['Pure 2x2 with cleaning: 12 refinement runs retained the source at the memory limit',
                    'Matched strict-FIFO wafer-vs-Pjob computational comparison absent'],
        evidence='verified_supplements.json')
    dump(HERE / 'claim_evidence.json', claims)
    completion = dict(source_sha256=sha(src), pdf_sha256=sha(pdf), pages=17,
        bibliography_entries=31, numbered_equations=39, original_equations_preserved=38,
        compilation_passes=build['compilation_passes'], undefined_references=0,
        duplicate_labels=0, overfull_boxes=0, visual_review_completed=True,
        reviewed_page_overviews=list(range(1,18)), enlarged_pages=[1,4,5,12,14,15,16],
        new_original_model_replays=114, additional_hybrid_start_replays=12,
        old_metadata_hashes_checked=1812, final_new_metadata_checks=len(source_hashes),
        raw_results_and_frozen_solver_unchanged=True, new_optimization_runs_started=0,
        statuses=dict(Counter(r['state'] for r in data['rows'])),
        review_report='REVIEW_CN.md', review_report_sha256=sha(HERE/'REVIEW_CN.md'),
        evidence_sha256=sha(HERE/'verified_supplements.json'))
    dump(HERE / 'completion_review.json', completion)
    package = PAPER / 'output/JMS_CN_supplement_review_20261101.zip'
    files = {src: 'JMS_Review_CN.tex', pdf: 'JMS_Review_CN.pdf'}
    figure_names = re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',text)
    for name in figure_names:
        candidates = [p for p in (PAPER/'figures').rglob(name+'.*') if p.suffix.lower() in ('.pdf','.png','.jpg','.jpeg','.eps')]
        assert candidates, name
        for p in candidates:
            files[p] = p.relative_to(PAPER).as_posix()
    for name in ('REVIEW_CN.md','completion_review.json','claim_evidence.json','verified_supplements.json',
                 'audit_supplements.py','manuscript.patch'):
        files[HERE/name] = 'review/'+name
    manifest = {target: sha(path) for path,target in files.items()}
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for path,target in files.items():
            z.write(path,target)
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        z.writestr('README.txt','Chinese manuscript updated from 114 verified supplement records.\nCompile with XeLaTeX (three passes), using elsarticle and ctex.\nReview/ contains evidence and open reviewer questions; it is separate from the submission body.\nRaw campaigns and frozen solvers remain in the research workspace.\n')
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for target,expected in manifest.items():
            assert hashlib.sha256(z.read(target)).hexdigest() == expected
    dump(HERE / 'package_receipt.json',dict(path=str(package),sha256=sha(package),bytes=package.stat().st_size,files=len(files)))
    print(json.dumps(dict(pages=17, revalidated_results=114, preserved_original_equations=38,
        package=str(package), package_bytes=package.stat().st_size, pdf_sha256=sha(pdf)),ensure_ascii=False))


if __name__ == '__main__':
    main()
