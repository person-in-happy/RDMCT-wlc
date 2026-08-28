from pathlib import Path
import subprocess
from PIL import Image
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parent
SRC = OUT.parent / 'figures'
OUT.mkdir(exist_ok=True)

BLUE = '#0072B2'
ORANGE = '#D55E00'
CYAN = '#56B4E9'
TEAL = '#009E73'
PURPLE = '#CC79A7'
GREY = '#6B7280'
LIGHT_GREY = '#DCE3EA'
PALE_GREY = '#EAF4FB'
PALE_ORANGE = '#FBEFE8'
BLACK = '#1F2933'

mpl.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Noto Sans CJK JP', 'Microsoft YaHei', 'SimHei', 'Arial', 'DejaVu Sans'],
    'font.size': 8.5,
    'axes.labelsize': 8.5,
    'xtick.labelsize': 7.8,
    'ytick.labelsize': 7.8,
    'legend.fontsize': 7.5,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'axes.unicode_minus': False,
    'figure.facecolor': 'white',
    'savefig.facecolor': 'white',
    'axes.linewidth': 0.7,
    'xtick.major.width': 0.7,
    'ytick.major.width': 0.7,
    'xtick.major.size': 3.2,
    'ytick.major.size': 3.2,
})


def clean_axis(ax):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(direction='out', color=BLACK, labelcolor=BLACK)
    ax.xaxis.label.set_color(BLACK)
    ax.yaxis.label.set_color(BLACK)


def panel(ax, letter):
    ax.text(-0.14, 1.02, letter, transform=ax.transAxes, fontsize=10, fontweight='bold',
            va='bottom', ha='left', color=BLACK)


def save(fig, stem):
    fig.savefig(OUT / f'{stem}.pdf', bbox_inches='tight', pad_inches=0.03)
    fig.savefig(OUT / f'{stem}.png', dpi=300, bbox_inches='tight', pad_inches=0.03)
    plt.close(fig)


def fig01_validation_cn():
    sizes = np.array([8, 16])
    cmax = {'纯4×1': np.array([610, 944]), '纯2×2': np.array([768, 1136]), '1:1混跑': np.array([834, 1170])}
    throughput = {k: 3600.0 * sizes / v for k, v in cmax.items()}
    overhead = {'纯2×2': 100.0 * (cmax['纯2×2'] / cmax['纯4×1'] - 1.0),
                '1:1混跑': 100.0 * (cmax['1:1混跑'] / cmax['纯4×1'] - 1.0)}
    styles = {
        '纯4×1': dict(color=BLUE, linestyle='-', marker='o', markerfacecolor=BLUE),
        '纯2×2': dict(color=ORANGE, linestyle='--', marker='s', markerfacecolor='white'),
        '1:1混跑': dict(color=TEAL, linestyle=':', marker='^', markerfacecolor='white'),
    }
    fig, axes = plt.subplots(3, 1, figsize=(3.6, 5.7))
    ylabels = [r'最优 $C_{\max}$ (s)', '等效吞吐率 (片/h)', '相对纯4×1完工时间增幅 (%)']
    offsets_a = {'纯4×1': (0, -13), '纯2×2': (-8, 7), '1:1混跑': (8, 8)}
    offsets_b = {'纯4×1': (0, 8), '纯2×2': (-8, 8), '1:1混跑': (8, -13)}
    for label in cmax:
        axes[0].plot(sizes, cmax[label], linewidth=1.35, markersize=5.2, markeredgecolor=BLACK,
                     markeredgewidth=0.7, label=label, **styles[label])
        axes[1].plot(sizes, throughput[label], linewidth=1.35, markersize=5.2, markeredgecolor=BLACK,
                     markeredgewidth=0.7, label=label, **styles[label])
        for xv, yv in zip(sizes, cmax[label]):
            axes[0].annotate(f'{yv:.0f}', (xv, yv), xytext=offsets_a[label], textcoords='offset points',
                             ha='center', fontsize=6.8, fontweight='bold' if label == '纯4×1' else 'normal')
        for xv, yv in zip(sizes, throughput[label]):
            axes[1].annotate(f'{yv:.2f}', (xv, yv), xytext=offsets_b[label], textcoords='offset points',
                             ha='center', fontsize=6.8, fontweight='bold' if label == '纯4×1' else 'normal')
    for i in (0,1):
        axes[i].set_xticks(sizes)
        axes[i].set_xlabel('晶圆数 (片)')
        axes[i].set_ylabel(ylabels[i])
        axes[i].set_ylim(0, max(max(v) for v in (cmax if i == 0 else throughput).values()) * 1.18)
        clean_axis(axes[i]); panel(axes[i], 'ab'[i])
    x = np.arange(len(sizes)); width = 0.34
    bars22 = axes[2].bar(x - width/2, overhead['纯2×2'], width, facecolor=PALE_ORANGE, edgecolor=ORANGE,
                         linewidth=0.8, hatch='////', label='纯2×2')
    barsmx = axes[2].bar(x + width/2, overhead['1:1混跑'], width, facecolor='#DDF3EA', edgecolor=TEAL,
                         linewidth=0.8, hatch='xx', label='1:1混跑')
    for bars in (bars22, barsmx):
        for bar in bars:
            h = bar.get_height()
            axes[2].text(bar.get_x()+bar.get_width()/2, h+0.9, f'{h:.2f}', ha='center', va='bottom', fontsize=6.8)
    axes[2].set_xticks(x, [str(v) for v in sizes])
    axes[2].set_xlabel('晶圆数 (片)')
    axes[2].set_ylabel(ylabels[2])
    axes[2].set_ylim(0, max(overhead['纯2×2'].max(), overhead['1:1混跑'].max())*1.24)
    clean_axis(axes[2]); panel(axes[2], 'c')
    handles = [Line2D([0], [0], color=styles[k]['color'], linestyle=styles[k]['linestyle'], marker=styles[k]['marker'],
               markerfacecolor=styles[k]['markerfacecolor'], markeredgecolor=BLACK, markersize=5, linewidth=1.2, label=k)
               for k in cmax]
    fig.legend(handles=handles, loc='lower center', ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.01))
    fig.subplots_adjust(left=0.2, right=0.98, bottom=0.1, top=0.98, hspace=0.55)
    save(fig, 'fig01_validation_cn')


def dot_panel(ax, values, labels, xlabel, decimals, focus_idx, baseline_indices=(0,2)):
    y = np.arange(len(labels))
    span = max(values) - min(values)
    pad = span * 0.15 if span else max(abs(values[0])*0.05,1)
    ax.axhspan(len(labels)-1-0.38, len(labels)-1+0.38, color=PALE_GREY, zorder=0)
    for bi in baseline_indices:
        ax.axhspan(bi-0.34, bi+0.34, facecolor='white', edgecolor=GREY, linewidth=0.55, hatch='////', zorder=0)
    ax.hlines(y, min(values)-pad*0.2, values, color=LIGHT_GREY, linewidth=0.7, zorder=1)
    for idx, (xv, yv) in enumerate(zip(values, y)):
        is_complete = idx == len(labels) - 1
        is_best = idx == focus_idx
        is_base = idx in baseline_indices
        marker = 'D' if is_complete else 'o'
        face = BLUE if is_complete else (ORANGE if idx == baseline_indices[0] else (TEAL if idx == baseline_indices[1] else CYAN))
        if not is_complete and not is_base:
            face = CYAN
        size = 52 if is_complete else (40 if is_base else 25)
        lw = 0.95 if (is_complete or is_base) else 0.45
        ax.scatter([xv],[yv],marker=marker,c=[face],s=size,edgecolors=BLACK,linewidths=lw,zorder=4 if is_complete else 3)
        ax.text(xv + pad*0.1, yv, f'{xv:.{decimals}f}', va='center', ha='left', fontsize=6.6,
                fontweight='bold' if (is_complete or is_base or is_best) else 'normal', color=BLACK)
    ax.set_xlim(min(values)-pad*0.35, max(values)+pad*1.9)
    ax.set_ylim(-0.6, len(labels)-0.2)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    clean_axis(ax)


def fig02_nominal_cn():
    labels = ['纯SCIP基线', 'ACS组件消融', 'HEM基线', 'HEM+Beam消融', '仅23D角色消融', '结构+贪心消融', '完整RDMCT-HBS']
    datasets = [
        ([16919.01, 16854.87, 16823.18, 16829.59, 16620.91, 16598.11, 16585.70], 2, 6, '平均 PDI (越低越好)'),
        ([226.05, 222.34, 219.65, 219.95, 219.42, 218.44, 218.32], 2, 6, '平均求解时间 (s)'),
        ([119.54, 127.18, 127.24, 127.19, 125.33, 126.03, 126.01], 2, 0, '平均终止 gap (%)'),
        ([64.0, 62.0, 62.4, 62.4, 62.6, 63.2, 63.2], 1, 0, '证明最优率 (%)'),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(3.8, 7.3))
    for i, (vals, dec, best, xlabel) in enumerate(datasets):
        dot_panel(axes[i], vals, labels, xlabel, dec, best)
        panel(axes[i], 'abcd'[i])
    legend = [
        Line2D([0],[0], marker='o', color='none', markerfacecolor=ORANGE, markeredgecolor=BLACK, markersize=6, label='纯SCIP基线'),
        Line2D([0],[0], marker='o', color='none', markerfacecolor=TEAL, markeredgecolor=BLACK, markersize=6, label='HEM基线'),
        Line2D([0],[0], marker='o', color='none', markerfacecolor=CYAN, markeredgecolor=BLACK, markersize=6, label='组件消融'),
        Line2D([0],[0], marker='D', color='none', markerfacecolor=BLUE, markeredgecolor=BLACK, markersize=6, label='完整RDMCT-HBS')
    ]
    fig.legend(handles=legend, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.012), borderaxespad=0.0)
    fig.subplots_adjust(left=0.44, right=0.98, bottom=0.105, top=0.99, hspace=0.54)
    save(fig, 'fig02_nominal_cn')


def fig03_spbs_cn():
    labels = ['SPBS', '无初始解']
    data = [([100.00, 51.67], '可行 incumbent 获得率 (%)'), ([20278.78, 27473.05], '平均 PDI (越低越好)')]
    fig, axes = plt.subplots(2, 1, figsize=(3.6, 3.7))
    for i, (vals, ylabel) in enumerate(data):
        bars = axes[i].bar(np.arange(2), vals, width=0.58, color=[BLUE, PALE_ORANGE], edgecolor=[BLUE, ORANGE], linewidth=0.8)
        bars[0].set_hatch('////'); bars[1].set_hatch('..')
        axes[i].set_xticks(np.arange(2), labels)
        axes[i].set_ylabel(ylabel)
        axes[i].set_ylim(0, max(vals)*1.25)
        for b,v in zip(bars, vals):
            axes[i].text(b.get_x()+b.get_width()/2, v+max(vals)*0.03, f'{v:.2f}', ha='center', va='bottom', fontsize=6.8)
        clean_axis(axes[i]); panel(axes[i], 'ab'[i])
    fig.subplots_adjust(left=0.2, right=0.98, bottom=0.1, top=0.98, hspace=0.5)
    save(fig, 'fig03_spbs_cn')


def fig04_workflow_cn():
    labels = ['完整两阶段', '二次目标', '单阶段']
    datasets = [
        ([2596.01, 2469.47, 5398.60], '路线总等待 (s)'),
        ([296.33, 293.27, 952.57], '路线最大等待 (s)'),
        ([0.130, 0.134, 0.216], '节拍变异系数 (-)'),
        ([22.04, 60.18, 370.41], '节拍偏差 (s)'),
    ]
    fig, axes = plt.subplots(2,2, figsize=(4.2,4.7))
    colors = [BLUE, TEAL, PALE_ORANGE]; edges = [BLUE, TEAL, ORANGE]; hatches=['////','xx','']
    for i,(ax,(vals,ylabel)) in enumerate(zip(axes.flat,datasets)):
        bars = ax.bar(np.arange(3), vals, width=0.62, color=colors, edgecolor=edges, linewidth=0.8)
        for b,h in zip(bars,hatches): b.set_hatch(h)
        ax.set_xticks(np.arange(3), labels)
        plt.setp(ax.get_xticklabels(), rotation=18, ha='right')
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, max(vals)*1.28)
        for b,v in zip(bars,vals):
            txt = f'{v:.3f}' if v < 1 else f'{v:.2f}'
            ax.text(b.get_x()+b.get_width()/2, v+max(vals)*0.03, txt, ha='center', va='bottom', fontsize=6.5)
        clean_axis(ax); panel(ax, 'abcd'[i])
    legend = [Patch(facecolor=colors[i], edgecolor=edges[i], hatch=hatches[i], label=labels[i]) for i in range(3)]
    fig.legend(handles=legend, loc='lower center', ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.01))
    fig.subplots_adjust(left=0.14,right=0.98,bottom=0.16,top=0.98,wspace=0.34,hspace=0.62)
    save(fig, 'fig04_workflow_cn')


def fig05_doe_cn():
    x = np.array([8,16,24,32])
    data = [
        ([28.13, 1876.54, 31155.94, 32959.89], '平均 PDI'),
        ([100, 100, 36, 20], '证明最优率 (%)'),
        ([0.34, 33.86, 408.55, 433.20], '平均求解时间 (s)'),
    ]
    fig, axes = plt.subplots(3,1, figsize=(3.6,4.8))
    for i,(vals,ylabel) in enumerate(data):
        ax = axes[i]
        ax.plot(x, vals, color=BLUE, linewidth=1.4, marker='o', markersize=4.8, markerfacecolor='white', markeredgecolor=BLUE, markeredgewidth=0.8)
        for xv,yv in zip(x,vals):
            txt = f'{yv:.2f}' if yv != int(yv) else f'{int(yv)}'
            ax.annotate(txt,(xv,yv),xytext=(0,7),textcoords='offset points',ha='center',fontsize=6.5)
        ax.set_xticks(x)
        ax.set_xlabel('晶圆数 (片)')
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, max(vals)*1.23)
        clean_axis(ax); panel(ax,'abc'[i])
    fig.subplots_adjust(left=0.23, right=0.98, bottom=0.08, top=0.98, hspace=0.58)
    save(fig, 'fig05_doe_cn')


def fig06_ood_cn():
    labels = ['纯SCIP基线', 'ACS组件消融', 'HEM基线', 'HEM+Beam消融', '仅23D角色消融', '结构+贪心消融', '完整RDMCT-HBS']
    datasets = [
        ([73670.99, 70915.54, 73003.59, 73165.58, 74187.22, 73507.76, 73919.15], 2, 1, '分布外平均 PDI'),
        ([171.35, 160.78, 165.88, 167.04, 169.96, 168.54, 170.02], 2, 1, '分布外平均终止 gap (%)'),
    ]
    fig, axes = plt.subplots(2,1, figsize=(3.8,4.9))
    for i,(vals,dec,best,xlabel) in enumerate(datasets):
        dot_panel(axes[i], vals, labels, xlabel, dec, best)
        panel(axes[i], 'ab'[i])
    legend = [
        Line2D([0],[0], marker='o', color='none', markerfacecolor=ORANGE, markeredgecolor=BLACK, markersize=6, label='纯SCIP基线'),
        Line2D([0],[0], marker='o', color='none', markerfacecolor=TEAL, markeredgecolor=BLACK, markersize=6, label='HEM基线'),
        Line2D([0],[0], marker='o', color='none', markerfacecolor=CYAN, markeredgecolor=BLACK, markersize=6, label='组件消融'),
        Line2D([0],[0], marker='D', color='none', markerfacecolor=BLUE, markeredgecolor=BLACK, markersize=6, label='完整RDMCT-HBS')
    ]
    fig.legend(handles=legend, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.008), borderaxespad=0.0)
    fig.subplots_adjust(left=0.44, right=0.98, bottom=0.20, top=0.98, hspace=0.55)
    save(fig, 'fig06_ood_cn')


def render_pdf_to_png(src_pdf: Path, out_png: Path, dpi=300):
    cmd = ['pdftocairo', '-png', '-singlefile', '-r', str(dpi), str(src_pdf), str(out_png.with_suffix(''))]
    subprocess.run(cmd, check=True)


def crop_and_compose_gantt(src_pdf: Path, out_stem: str, row_labels, col_labels=('Wafer视角','Resource视角')):
    temp_png = OUT / f'{out_stem}_source.png'
    render_pdf_to_png(src_pdf, temp_png, dpi=300)
    im = Image.open(temp_png).convert('RGB')
    W,H = im.size
    if 'gantt8' in out_stem:
        boxes = [
            (int(0.07*W), int(0.125*H), int(0.50*W), int(0.252*H)),
            (int(0.59*W), int(0.125*H), int(0.97*W), int(0.25*H)),
            (int(0.07*W), int(0.38*H), int(0.50*W), int(0.62*H)),
            (int(0.59*W), int(0.38*H), int(0.97*W), int(0.58*H)),
            (int(0.07*W), int(0.72*H), int(0.50*W), int(0.93*H)),
            (int(0.59*W), int(0.72*H), int(0.97*W), int(0.91*H)),
        ]
    else:
        boxes = [
            (int(0.07*W), int(0.11*H), int(0.49*W), int(0.30*H)),
            (int(0.59*W), int(0.11*H), int(0.97*W), int(0.26*H)),
            (int(0.11*W), int(0.39*H), int(0.43*W), int(0.66*H)),
            (int(0.59*W), int(0.39*H), int(0.97*W), int(0.58*H)),
            (int(0.11*W), int(0.71*H), int(0.43*W), int(0.95*H)),
            (int(0.59*W), int(0.71*H), int(0.97*W), int(0.91*H)),
        ]
    crops = []
    for b in boxes:
        c = im.crop(b)
        # further trim per-panel embedded titles and footnotes while preserving axes
        top_trim = max(16, int(0.06 * c.height))
        bottom_trim = max(10, int(0.03 * c.height))
        c = c.crop((0, top_trim, c.width, c.height - bottom_trim))
        crops.append(c)

    fig = plt.figure(figsize=(12.4, 13.0), facecolor='white')
    gs = fig.add_gridspec(nrows=4, ncols=2, height_ratios=[1,1,1,0.16], width_ratios=[1,1], hspace=0.18, wspace=0.08)
    for j, title in enumerate(col_labels):
        axh = fig.add_subplot(gs[0, j])
        axh.set_title(title, fontsize=12, fontweight='bold', pad=8, color=BLACK)
        axh.axis('off')
    # place actual panels manually to preserve headers
    for idx, crop in enumerate(crops):
        r = idx//2
        c = idx%2
        ax = fig.add_subplot(gs[r, c])
        ax.imshow(crop)
        ax.axis('off')
        if c == 0:
            ax.text(-0.08, 0.5, row_labels[r], transform=ax.transAxes, rotation=90,
                    ha='center', va='center', fontsize=11, fontweight='bold', color=BLACK)
        if r == 2:
            ax.text(0.5, -0.06, '时间 (s)', transform=ax.transAxes,
                    ha='center', va='top', fontsize=10, color=BLACK)
    # Legend row
    axl = fig.add_subplot(gs[3, :]); axl.axis('off')
    legend_items = [
        Patch(facecolor='#4A90E2', edgecolor=BLACK, label='搬运动作'),
        Patch(facecolor='#B08B6F', edgecolor=BLACK, label='AL 对准'),
        Patch(facecolor='#6AAE5B', edgecolor=BLACK, label='装载锁相关'),
        Patch(facecolor='#F3A6A0', edgecolor=BLACK, label='腔室装/卸片'),
        Patch(facecolor='#E66863', edgecolor=BLACK, label='腔室加工'),
        Patch(facecolor='#B98BBE', edgecolor=BLACK, label='回片/下游处理'),
        Patch(facecolor='#C9C3BE', edgecolor=BLACK, label='等待/占位'),
    ]
    axl.legend(handles=legend_items, loc='center', ncol=7, frameon=False, fontsize=8.2)
    fig.savefig(OUT / f'{out_stem}.pdf', bbox_inches='tight', pad_inches=0.04)
    fig.savefig(OUT / f'{out_stem}.png', dpi=300, bbox_inches='tight', pad_inches=0.04)
    plt.close(fig)
    temp_png.unlink(missing_ok=True)


def main():
    fig01_validation_cn(); fig02_nominal_cn(); fig03_spbs_cn(); fig04_workflow_cn(); fig05_doe_cn(); fig06_ood_cn()
    crop_and_compose_gantt(SRC/'fig07_mode_gantt8.pdf', 'fig07_mode_gantt8', ['纯4×1','纯2×2','4:4 混跑'])
    crop_and_compose_gantt(SRC/'fig08_mode_gantt16.pdf', 'fig08_mode_gantt16', ['纯4×1','纯2×2','8:8 混跑'])

if __name__ == '__main__':
    main()
