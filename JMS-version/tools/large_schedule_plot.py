"""Complete resource plot and paginated wafer routes from validated events."""
from pathlib import Path
import hashlib,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.backends.backend_pdf import PdfPages
from current_defaults_swimlane import build,STYLE
from render_current_defaults_gantt import rows,COLORS


def draw(data, output, optimal):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    lanes,bars,traces,completed=build(data)
    flows,_=rows(data)
    horizon=max(b['end'] for b in bars)
    cmax=data['cmax']
    status='产品完工已证全局最优' if optimal else '已验证可行，未证全局最优'
    n=sum(j['product'] for j in data['jobs'])
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],
                         'axes.unicode_minus':False,'font.size':12,'pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(24,9))
    fig.subplots_adjust(left=.09,right=.99,bottom=.20,top=.88)
    pos={lane:i for i,lane in enumerate(lanes)}
    for i in range(len(lanes)):
        ax.axhspan(i-.45,i+.45,color='#f4f6f8' if i%2==0 else 'white',zorder=0)
    for b in bars:
        ax.broken_barh([(b['start'],b['end']-b['start'])],(pos[b['lane']]-.34,.68),
                       facecolors=STYLE[b['action']],edgecolors='white',linewidth=.12)
    for c in data['cycles']:
        title='清洁' if c['mode']=='clean' else c['mode'].replace('x','×')
        ax.text((c['start']+c['end'])/2,pos['旋转腔 CH'+str(c['chamber'])],title,
                ha='center',va='center',color='white',fontsize=8)
    ax.set_yticks(range(len(lanes)),lanes)
    ax.set_ylim(len(lanes)-.5,-.5);ax.set_xlim(0,horizon*1.025)
    ax.set_xlabel('时间 / s');ax.grid(axis='x',color='#dfe3e8',lw=.5)
    ax.set_axisbelow(True);ax.spines[['top','right','left']].set_visible(False)
    ax.axvline(cmax,color='#222222',ls='--',lw=1)
    ax.axvline(horizon,color='#666666',ls=':',lw=1)
    fig.suptitle(f'{n}片产品晶圆完整排程：{status}；Cmax={cmax:g} s；全部占用结束={horizon:g} s',fontsize=18)
    used={b['action'] for b in bars}
    fig.legend(handles=[Patch(facecolor=c,label=k) for k,c in STYLE.items() if k in used],
               loc='lower center',bbox_to_anchor=(.55,.055),ncol=7,frameon=False,fontsize=12)
    fig.text(.55,.022,'完整显示加工、清洁、搬运及装载锁复位；隐式动作只作可行时序补全，不改取放与加工时刻。',ha='center')
    for ext in ('pdf','png','svg'):fig.savefig(output/f'gantt_resources.{ext}',dpi=180,facecolor='white')
    plt.close(fig)
    labels=list(dict.fromkeys(f[0] for f in flows))
    with PdfPages(output/'wafer_routes.pdf') as pdf:
        for start in range(0,len(labels),25):
            selected=labels[start:start+25];pos={label:i for i,label in enumerate(selected)}
            fig,ax=plt.subplots(figsize=(18,11))
            fig.subplots_adjust(left=.23,right=.99,top=.90,bottom=.17)
            for label,a,b,kind in flows:
                if label in pos:
                    ax.broken_barh([(a,b-a)],(pos[label]-.32,.64),
                                   facecolors=COLORS[kind],edgecolors='white',linewidth=.2)
            ax.set_yticks(range(len(selected)),selected,fontsize=10)
            ax.set_ylim(len(selected)-.5,-.5);ax.set_xlim(0,horizon*1.02)
            ax.set_xlabel('时间 / s');ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
            ax.axvline(cmax,color='#333333',ls='--',lw=1)
            fig.suptitle(f'完整晶圆路线 {start+1}—{start+len(selected)} / {len(labels)}；{status}',fontsize=17)
            used={f[3] for f in flows if f[0] in pos}
            fig.legend(handles=[Patch(facecolor=c,label=k) for k,c in COLORS.items() if k in used],
                       loc='lower center',bbox_to_anchor=(.60,.045),ncol=4,frameon=False)
            pdf.savefig(fig,facecolor='white')
            plt.close(fig)
    evidence=dict(resource_end=horizon,cmax=cmax,certified_global_optimum=optimal,
                  products=n,complete_wafer_paths=len(traces),explicit_events_covered=len(data['events']),
                  cycles_by_mode={mode:sum(c['mode']==mode for c in data['cycles']) for mode in ('4x1','2x2','clean')},
                  bars=bars,paths=traces,implicit_action_completions=completed,
                  optimization_calls=0,renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'figure_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(output=str(output),products=n,certified_global_optimum=optimal),ensure_ascii=False))
