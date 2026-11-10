from pathlib import Path
from collections import defaultdict
from statistics import mean
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
rows = json.loads((HERE/'verified_results.json').read_text('utf-8'))['rows']
font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':8,'axes.labelsize':8,
                     'axes.titlesize':9,'axes.spines.top':False,'axes.spines.right':False,
                     'pdf.fonttype':42,'ps.fonttype':42,'axes.unicode_minus':False})
fig, axes = plt.subplots(1,3,figsize=(7.2,2.6),layout='constrained')
styles=[('4x1',r'$4\times1$','#0072B2','o'),('2x2',r'$2\times2$','#D55E00','s'),('mixed','混合','#009E73','^')]
data=[]
for ax,n in zip(axes,(8,16,24)):
    for recipe,label,color,marker in styles:
        groups=defaultdict(list)
        for r in rows:
            if r['suite']=='crossover' and r['product_count']==n and f'_{recipe}_' in r['case']:
                groups[r['h']].append(r['upper'])
        xs=sorted(groups)
        ys=[mean(groups[h]) for h in xs]
        errors=[[mean(groups[h])-min(groups[h]) for h in xs],[max(groups[h])-mean(groups[h]) for h in xs]]
        ax.errorbar(xs,ys,yerr=errors,label=label,color=color,marker=marker,markersize=3.5,
                    capsize=2,linewidth=1.2,elinewidth=.8)
        data.append({'n':n,'recipe':recipe,'h':xs,'means':ys,'ranges':[groups[h] for h in xs]})
    ax.set_title(f'{n}片产品晶圆')
    ax.set_xlabel('清洁阈值 $H$')
    ax.set_xticks(range(3,11))
    ax.grid(axis='y',color='#dddddd',linewidth=.5)
    ax.tick_params(length=3)
axes[0].set_ylabel('可行完工时间 $C_{\\max}$ / s')
axes[0].legend(loc='upper right',frameon=False,fontsize=7)
out=PAPER/'figures/final_results_cn'
out.mkdir(exist_ok=True)
fig.savefig(out/'fig_threshold_verified_cn.pdf')
fig.savefig(out/'fig_threshold_verified_cn.png',dpi=250)
(HERE/'figure_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
print(out/'fig_threshold_verified_cn.pdf')
