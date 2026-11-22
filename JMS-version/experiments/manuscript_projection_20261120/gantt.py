from collections import defaultdict
from pathlib import Path
import sys

JMS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(JMS/'tools'))
from render_journal_schedule_examples import LEGEND, LEGEND_LABELS, STYLE, build, plt
from matplotlib.patches import Patch


def draw(data, folder):
    folder.mkdir(parents=True,exist_ok=True)
    lanes,bars,_,_=build(data)
    finish=data['cmax']
    last=max(b['end'] for b in bars)
    colors={**STYLE,'4×1加工':STYLE['腔室加工'],'2×2加工':'#DB8970'}
    bands=defaultdict(list)
    for item in bars:
        lane,action=item['lane'],item['action']
        if action=='腔室加工':
            cycle,=[c for c in data['cycles'] if lane==f"旋转腔 CH{c['chamber']}" and c['start']-1e-5<=item['start'] and c['end']+1e-5>=item['end']]
            action=cycle['mode'].replace('x','×')+'加工'
        bands[lane,action].append((item['start'],item['end']-item['start']))
    present={a for _,a in bands}
    order=[x for x in [*LEGEND,'4×1加工','2×2加工','清洁'] if x in present]
    order=list(dict.fromkeys(order))
    if set(order)!=present: raise ValueError(f'Unrepresented actions: {present-set(order)}')
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(12,1.45+.29*len(lanes)))
    fig.subplots_adjust(left=.13,right=.98,bottom=.21,top=.96)
    for y,lane in enumerate(lanes):
        ax.axhspan(y-.45,y+.45,color='#f5f6f8' if y%2==0 else 'white',zorder=0)
        for action in order:
            if (lane,action) in bands:
                ax.broken_barh(bands[lane,action],(y-.33,.66),facecolors=colors[action],edgecolors='none')
    ax.set(yticks=range(len(lanes)),yticklabels=lanes,ylim=(len(lanes)-.5,-.5),xlim=(0,last*1.025),xlabel='时间 / s')
    ax.grid(axis='x',alpha=.25)
    a=ax.axvline(finish,ls='--',color='#252525',lw=1,label='末片产品返回')
    b=ax.axvline(last,ls=':',color='#606060',lw=1,label='设备占用结束')
    handles=[Patch(facecolor=colors[s],label=LEGEND_LABELS.get(s,s)) for s in order]+[a,b]
    fig.legend(handles=handles,loc='lower center',ncol=7,frameon=False,fontsize=9)
    for ext in ('pdf','png','svg'):
        fig.savefig(folder/('gantt.'+ext),dpi=180,facecolor='white')
    plt.close(fig)
    return dict(product_return=finish,equipment_end=last,lanes=len(lanes),intervals=len(bars),events=len(data['events']))
