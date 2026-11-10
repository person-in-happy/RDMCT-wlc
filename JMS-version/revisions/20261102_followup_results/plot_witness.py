from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
data=json.loads((HERE/'newrule_validation.json').read_text('utf-8'))
rows=data['rows']
sync=next(r for r in rows if r['category']=='new_exact' and r['cell']['id']=='n2_H3_4x1_dual_same_lp__pjob')
parallel=next(r for r in rows if r['category']=='new_exact' and r['cell']['id']=='n2_H3_4x1_dual__wafer')
assert sync['valid'] and parallel['valid']
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':font.get_name(),'font.size':10,'axes.unicode_minus':False,'pdf.fonttype':42})
fig, axes=plt.subplots(1,2,figsize=(10,2.7),layout='constrained')
blue,orange='#0072B2','#D55E00'
ax=axes[0]
for index,p in enumerate(sync['picks']):
    y=1-index
    ax.plot([p['loan_start'],p['loan_end']],[y,y],color='#8b9299',lw=1.6,zorder=1)
    ax.scatter([p['loan_start']],[y],c=blue,s=35,zorder=4)
    ax.scatter([p['loan_end']],[y],marker='s',c=blue,s=30,zorder=4)
    ax.broken_barh([(104,180)],(y-.14,.28),facecolors=blue,zorder=3)
ax.set_yticks([0,1],['Pjob1[2]','Pjob1[1]'])
ax.set_title('(a) 同Pjob、同LP同步取片',loc='left',pad=16)
ax.text(0,1.23,'0 s取片',ha='left',fontsize=9)
ax.text(324,1.23,'324 s回片',ha='right',fontsize=9)
ax.text(194,.5,'CH2: 104–284 s',ha='center',fontsize=9,color=blue)
ax=axes[1]
for y,chamber,color in ((1,2,blue),(0,3,orange)):
    c=next(c for c in parallel['cycles'] if c['chamber']==chamber and c['mode']=='4x1')
    ax.broken_barh([(c['start'],c['end']-c['start'])],(y-.14,.28),facecolors=color,zorder=3)
    ax.text(c['start'],y+.23,f'{c["start"]:.0f}–{c["end"]:.0f} s',ha='left',fontsize=9,color=color)
ax.axvspan(104,267,color='#009E73',alpha=.10,zorder=1)
ax.annotate('',xy=(104,.5),xytext=(267,.5),arrowprops=dict(arrowstyle='<->',lw=1.2,color='#00734f'))
ax.text(185.5,.6,'生产重叠163 s',ha='center',fontsize=9,color='#00734f')
ax.set_yticks([0,1],['CH3','CH2'])
ax.set_title('(b) 跨LP产品的双腔生产',loc='left',pad=16)
for ax in axes:
    ax.set_xlim(-10,340);ax.set_ylim(-.45,1.55)
    ax.set_xticks([0,60,120,180,240,300]);ax.set_xlabel('时间 / s')
    ax.grid(axis='x',alpha=.18,zorder=0)
    ax.spines[['top','right','left']].set_visible(False)
    ax.tick_params(axis='y',length=0)
dest=PAPER/'figures/final_results_cn';dest.mkdir(exist_ok=True)
fig.savefig(dest/'fig_nondecreasing_witness_cn.pdf',bbox_inches='tight')
fig.savefig(dest/'fig_nondecreasing_witness_cn.png',dpi=220,bbox_inches='tight')
plt.close(fig)
print('Saved representative schedule figure from validated new-rule assignments.')
