"""Read-only full-D assignment checks; deterministic figure from saved events."""
from pathlib import Path
import sys
import json
import hashlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'JMS-version/tools'))
import journal_support_experiments as j

OUT = Path(__file__).resolve().parent
SOURCE = j.base.SMALL / 'runs/n1_H2_2x2_dual__s1__scip'


def audit():
    records = []
    for phase, assignment in [('phase1', 'variables_phase1'), ('result', 'variables')]:
        p, v = SOURCE / (phase+'.json'), SOURCE / (assignment+'.json')
        d = j.read(p)
        records.append(dict(source=str(p), sha256=j.digest(p), variables_sha256=j.digest(v),
                            metrics=j.metrics(d), full_model_audit=j.checked_result(d, v),
                            status=d['status'], primary_bound=d.get('primary_bound', d['dual_bound']),
                            solver_started=False))
    manifest = j.read(SOURCE / 'manifest.json')
    checked = {}
    for rel, expected in manifest['assets'].items():
        actual = j.digest(ROOT / rel)
        if actual != expected:
            raise RuntimeError('Historical backend asset differs: '+rel)
        checked[rel] = actual
    if j.digest(SOURCE / 'model.lp.gz') != manifest['lp_sha256']:
        raise RuntimeError('Historical LP hash mismatch')
    j.dump(OUT / 'witness_evidence.json', dict(records=records, assets=checked,
                                             lp_sha256=manifest['lp_sha256'], manifest_sha256=j.digest(SOURCE/'manifest.json')))
    print(json.dumps(records, ensure_ascii=False, indent=2))


def figure():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False, 'pdf.fonttype': 42})
    d = j.read(SOURCE / 'result.json')
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), gridspec_kw={'height_ratios': [1, 2.2]}, sharex=True, layout='constrained')
    process, clean, loan = '#346995', '#317957', '#d7e4ef'
    for c in d['cycles']:
        color = clean if c['mode'] == 'clean' else process
        axes[0].broken_barh([(c['start'], c['end']-c['start'])], (0, .65), facecolors=color)
        axes[0].text((c['start']+c['end'])/2, .325, '清洁（四片辅助片）' if c['mode']=='clean' else '2×2', ha='center', va='center', color='white', fontsize=10)
    product = next(x for x in d['jobs'] if x['product'])
    axes[0].broken_barh([(product['loan_start'], product['loan_end']-product['loan_start'])], (1, .55), facecolors=loan, edgecolors=process)
    axes[0].text(160, 1.275, '产品LP1_W1：同一PW对连续两次加工', ha='center', va='center', fontsize=9)
    axes[0].set_yticks([.325, 1.275], ['CH2周期', '产品借还'])
    axes[0].set_ylim(-.2, 1.8)
    axes[0].set_title('配置D：1片2×2，H=2，8片辅助片；固定结构第二阶段排程', loc='left', fontsize=12)
    pair_mode = {p['id']: p['mode'] for p in d['pairs']}
    for x in d['jobs']:
        if x['product']:
            continue
        y = 7 - int(x['identity'][1:])
        color = clean if pair_mode[x['pair']] == 'clean' else process
        axes[1].broken_barh([(x['loan_start'], x['loan_end']-x['loan_start'])], (y-.3, .6), facecolors=color)
    axes[1].set_yticks(range(7), [f'D{i}' for i in range(7, 0, -1)])
    axes[1].set_ylim(-.6, 6.8)
    axes[1].set_ylabel('辅助片借用区间')
    axes[1].set_xlabel('时间 / s')
    axes[1].set_title('D2、D3归还后再次用于清洁；借用9次，实际使用7片，同时借用峰值5片', loc='left', fontsize=10)
    for ax in axes:
        ax.axvline(303, ls='--', color='#a74337', lw=1.3)
        ax.axvline(796, ls=':', color='#333333', lw=1.3)
        ax.grid(axis='x', color='#dddddd', alpha=.65)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].text(310, 1.65, '产品完工303 s', color='#a74337', fontsize=9)
    axes[0].text(785, 1.65, '占用结束796 s', ha='right', fontsize=9)
    axes[1].set_xlim(0, 820)
    target = ROOT / 'JMS-version/figures/fig_d_coupled_witness_cn'
    for ext in ('pdf', 'png'):
        fig.savefig(target.with_suffix('.'+ext), dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    audit()
    if '--figure' in sys.argv:
        figure()
