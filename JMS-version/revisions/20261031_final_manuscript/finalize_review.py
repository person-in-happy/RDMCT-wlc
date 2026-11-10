"""Check manuscript evidence links and package the final Chinese source."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json
import re
import zipfile

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent
BUILD = PAPER / 'output/model4_cn_build'
DATE = '2026-11-01'
VISUALLY_REVIEWED_PDF = 'c01d8ca3e790b8621173951c9ff805a09948ea72fbc3f758f35722d1c80b9bbe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text('utf-8'))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def main():
    source_path = PAPER / 'JMS_Review_CN.tex'
    pdf_path = PAPER / 'JMS_Review_CN.pdf'
    source = source_path.read_text('utf-8')
    original = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
    verified = read(HERE / 'verified_results.json')
    stats = read(HERE / 'statistics.json')
    build = read(BUILD / 'build_report.json')
    assert sha(source_path) == build['source_sha256']
    assert sha(pdf_path) == build['pdf_sha256']
    assert sha(pdf_path) == VISUALLY_REVIEWED_PDF, 'A new PDF needs visual review before finalization'
    assert sha(PAPER / 'output/pdf/JMS_Review_CN.pdf') == sha(pdf_path)
    assert sha(PAPER / 'model4_pjob_fifo_20261029/model.py') == verified['source_assets_sha256']

    rows = verified['rows']
    assert len(rows) == verified['completed'] == 453
    assert sum(r['has_solution'] for r in rows) == verified['feasible'] == 441
    assert len(verified['failures']) == 3
    assert all(r['variant'] == 'cold' for r in rows if not r['has_solution'])
    assert all(c['expected'] == c['validated'] + c['failures'] for c in verified['campaigns'])

    # Audit hashes and small result files are checked again at handoff. The
    # complete model/assignment/physical validation is recorded in verified_results.
    metadata_checks = 0
    for c in verified['campaigns']:
        assert sha(Path(c['audit'])) == c['audit_sha256'], c['name']
    for r in rows:
        run = PAPER / 'results' / r['campaign'] / 'runs' / r['id']
        for name in ('result.json', 'phase1.json', 'evidence.json', 'manifest.json'):
            assert sha(run / name) == r['hashes'][name], str(run / name)
            metadata_checks += 1
    print(f'Final metadata verified: {metadata_checks} files', flush=True)

    numbered = r'\\begin\{equation\}(.*?)\\end\{equation\}'
    original_equations = re.findall(numbered, original, re.S)
    final_equations = re.findall(numbered, source, re.S)
    assert original_equations == final_equations
    assert len(final_equations) == 38
    backmatter = r'\section*{CRediT'
    assert original.split(backmatter, 1)[1] == source.split(backmatter, 1)[1]
    abstract_prefix = original.split(r'\begin{abstract}', 1)[1].split('实验中，对330个候选排程', 1)[0]
    assert source.split(r'\begin{abstract}', 1)[1].startswith(abstract_prefix)
    bibs = re.findall(r'\\bibitem\{([^}]+)\}', source)
    cites = {key.strip() for group in re.findall(r'\\cite\w*\{([^}]+)\}', source) for key in group.split(',')}
    assert len(bibs) == len(set(bibs)) == 31 and set(bibs) == cites
    for forbidden in ('匿名', '模型4', '模型2', 'TODO', 'TBD'):
        assert forbidden not in source, forbidden
    assert r'\section{不足' not in source and r'\subsection{局限' not in source

    def selected(suite, variant=None):
        return [r for r in rows if r['suite'] == suite and (variant is None or r['variant'] == variant)]

    def keys(selected_rows):
        return [{'campaign': r['campaign'], 'cell': r['id']} for r in selected_rows]

    refinement = selected('paper', 'refined')
    assert len(refinement) == 24
    percentages = [100 * (r['phase1_metrics']['route_wait_sum'] - r['metrics']['route_wait_sum']) /
                   r['phase1_metrics']['route_wait_sum'] for r in refinement]
    assert f'{min(percentages):.2f}' == '15.63' and f'{max(percentages):.2f}' == '63.03'
    assert all(abs(r['metrics']['route_wait_max'] - 65) < 1e-6 for r in refinement)
    assert all(r['upper'] <= r['phase1_cmax'] + 1.001e-6 for r in refinement)
    assert len(stats['rhythm_pairing']) == 12
    assert all(p['same_primary_assignment_within_tolerance'] for p in stats['rhythm_pairing'])
    assert stats['proposed_scip_identical_cmax_pairs'] == 24
    assert f"{min(r['percent'] for r in stats['initialization']):.2f}" == '1.91'
    assert f"{max(r['percent'] for r in stats['initialization']):.2f}" == '9.96'
    scale_original = [r for r in selected('scale32') if 'memory_retry' not in r['campaign']]
    scale_retry = [r for r in selected('scale32') if 'memory_retry' in r['campaign']]
    assert len(scale_original) == 6 and len(scale_retry) == 3
    assert {r['case'] for r in scale_retry} == {r['case'] for r in verified['failures']}
    assert {r['seed'] for r in scale_retry} == {1, 2, 3}
    assert all(r['status'] == 'memlimit' and r['has_solution'] for r in scale_retry)

    evidence = {
        'date': DATE,
        'source_sha256': sha(source_path),
        'verified_results_sha256': sha(HERE / 'verified_results.json'),
        'statistics_sha256': sha(HERE / 'statistics.json'),
        'abstract_and_conclusion': {
            'coverage': {'completed': 453, 'feasible': 441, 'execution_interrupted': 3},
            'stage_within_run_wait_reduction_percent': [min(percentages), max(percentages)],
            'refinement_cells': keys(refinement),
            'rhythm_cells': keys(selected('rhythm')),
            'initialization_cases': stats['initialization'],
        },
        'table_evidence': {
            'tab:coverage-cn': [{'campaign': c['name'], 'complete': c['validated'],
                                  'feasible': c['feasible'], 'interrupted': c['failures']}
                                 for c in verified['campaigns']],
            'tab:model4-enumeration-cn': {
                'manifest': 'JMS-version/gif/kexingyu/pjob_fifo_20261029/manifest.json',
                'prior_validation': 'JMS-version/revisions/20261029_pjob_index_encoding/strict_order_audit.json',
                'export_counts': {'8': 6720, '16': 676, '32': 6},
                'constructive_family_lower_bounds': stats['constructive_counts'],
            },
            'tab:refinement-cn': keys(refinement + selected('qualification')),
            'tab:rhythm-ablation-cn': keys(selected('rhythm')),
            'tab:initialization-cn': keys([r for r in selected('paper')
                                          if r['case'] in {s['case'] for s in stats['initialization']}
                                          and r['variant'] in ('cold', 'serial', 'joint')]),
            'tab:cuts-cn': keys(selected('paper_cuts')),
            'tab:scale32-cn': keys(scale_original + scale_retry),
        },
        'figure_evidence': {'fig:threshold-results-cn': keys(selected('crossover'))},
        'qualification_cells': keys(selected('qualification')),
        'fixed_structure_cells': keys([r for r in selected('paper') if r['variant'] in ('fixed', 'partition')]),
    }
    dump(HERE / 'claim_evidence.json', evidence)

    figures = []
    graphicpaths = re.findall(r'\{([^{}]+/)\}', re.search(r'\\graphicspath\{(.+)\}', source).group(1))
    for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', source):
        match = next((PAPER / directory / (name + ext) for directory in graphicpaths
                      for ext in ('.pdf', '.png', '.jpg', '.jpeg')
                      if (PAPER / directory / (name + ext)).is_file()), None)
        assert match is not None, name
        figures.append(match)
    assert len(figures) == 5

    package_path = PAPER / 'output/JMS_CN_final_20261101.zip'
    package_files = [source_path, pdf_path, *figures]
    manifest = {str(path.relative_to(PAPER)).replace('\\', '/'): sha(path) for path in package_files}
    readme = '''# 中文终稿文件包

版本：2026-11-01。

本包包含中文稿件 LaTeX 源码、编译后的 PDF，以及正文引用的五幅图。图片目录顺序与源文件一致。

## 编译

使用带有 XeLaTeX、elsarticle、ctex 和 Fandol 字体的 TeX 环境。在解压后的目录运行以下命令三次，使交叉引用完成更新：

```powershell
xelatex -interaction=nonstopmode -halt-on-error JMS_Review_CN.tex
```

参考文献直接保存在主源码中，无需运行 BibTeX。文件编码为 UTF-8。PDF 为 16 页。

`SHA256.json`记录本包源码、PDF及五幅图片的摘要。实验统计和本轮修改记录保存在项目的 `JMS-version/revisions/20261031_final_manuscript/` 中。
'''
    with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in package_files:
            archive.write(path, path.relative_to(PAPER).as_posix())
        archive.writestr('README_CN.md', readme)
        archive.writestr('SHA256.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(package_path) as archive:
        assert archive.testzip() is None
        for name, expected in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected, name

    report = {
        'date': DATE,
        'scope': 'Chinese final manuscript; raw experiments and English/other-copy manuscripts unchanged by this task',
        'original_source_sha256': sha(HERE / 'original/JMS_Review_CN.tex'),
        'source_sha256': sha(source_path), 'pdf_sha256': sha(pdf_path),
        'package': str(package_path.relative_to(ROOT)), 'package_sha256': sha(package_path),
        'build': build,
        'completed_runs': 453, 'validated_feasible_schedules': 441,
        'no_incumbent_cold_runs': 12, 'original_execution_interruptions': 3,
        'replacement_scale_runs_completed_and_feasible': 3,
        'run_metadata_files_rechecked': metadata_checks,
        'numbered_equations_unchanged': len(final_equations),
        'abstract_background_preserved': True,
        'author_declarations_and_references_preserved': True,
        'reference_entries': len(bibs), 'uncited_references': [], 'missing_citations': [],
        'reference_check_scope': 'Internal citation-to-bibliography consistency; not a new source-by-source external literature review',
        'visual_review': {'page_count': 16, 'contact_sheets': [1, 7, 13],
                          'detailed_pages': [1, 3, 4, 5, 12, 13, 14, 15],
                          'latest_pdf_confirmation': 'confirmed',
                          'confirmed_pdf_sha256': VISUALLY_REVIEWED_PDF},
        'deferred_experiments_for_current_claims': [],
        'new_experiments_launched': False,
        'scientific_claim_boundaries': 'Feasible completion times; optimum claims only for the six fixed-structure solutions',
        'figure_files': {str(p.relative_to(PAPER)): sha(p) for p in figures},
    }
    dump(HERE / 'completion_review.json', report)
    patch = ''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
                    fromfile='original/JMS_Review_CN.tex', tofile='JMS-version/JMS_Review_CN.tex'))
    (HERE / 'manuscript.patch').write_text(patch, 'utf-8')
    experiment_start = source.index(r'\section{计算实验')
    (HERE / 'applied_experiment_section.tex').write_text(source[experiment_start:source.index(backmatter)], 'utf-8')
    print(json.dumps({'package': str(package_path), 'files': len(package_files),
                      'pages': build['pages'], 'equations': len(final_equations),
                      'references': len(bibs), 'pending_experiments': 0}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
