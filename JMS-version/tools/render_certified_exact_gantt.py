"""Render only after rechecking the exact-search/full-model proof chain."""
from pathlib import Path
import argparse,json
from verify_exact_optimality import verify,read,require,ROOT
from run_experiments import digest,dump
from render_optional_cleaning_gantt import chart_rows,wafer_rows,COLORS,FLOW_COLORS,LANES,plt,Patch


def checked_data(proof_path):
    proof=read(proof_path)
    require(proof.get('original_objective_globally_optimal') is True,'Not an original-model optimum certificate')
    fresh=verify(proof['search'],proof['original_certificate'])
    require({k:v for k,v in proof.items() if k!='certified_utc'}==
            {k:v for k,v in fresh.items() if k!='certified_utc'},'Proof content changed')
    data=read(Path(proof['search'])/'result.json')
    require(data.get('cleaning_policy')=='optional_before_threshold','Wrong cleaning policy')
    data['validation']=fresh['physical']
    return data,fresh


def draw(data,output,flow=False):
    rows=wafer_rows(data) if flow else chart_rows(data)
    lanes=list(dict.fromkeys(row[0] for row in rows)) if flow else LANES
    colors=FLOW_COLORS if flow else COLORS
    cmax=data['validation']['product_return_cmax']
    horizon=max(row[2] for row in rows)
    fig,ax=plt.subplots(figsize=(12,7 if flow else 6.4))
    fig.subplots_adjust(left=.12,right=.975,top=.82,bottom=.29)
    for row in rows:
        lane,start,end,kind=row[:4]
        if end>start:ax.broken_barh([(start,end-start)],(lanes.index(lane)-.32,.64),facecolors=colors[kind],edgecolors='none')
    ax.set_yticks(range(len(lanes)),lanes,fontsize=8 if flow else 10)
    ax.set_ylim(len(lanes)-.5,-.8);ax.set_xlim(0,horizon*1.015)
    ax.set_xlabel('时间 / s');ax.set_axisbelow(True);ax.grid(axis='x',color='#E3E7EA',linewidth=.6)
    ax.spines[['top','right']].set_visible(False);ax.axvline(cmax,color='#333333',linestyle='--',linewidth=1)
    n=sum(j['product'] for j in data['jobs']);h=data['config']['cleaning_interval']
    recipes=[r for r in ('4x1','2x2') if any(port[r] for port in data['config']['load_ports'].values())]
    recipe='/'.join(recipes).replace('x','×')
    fig.suptitle(f'{n}片纯{recipe}，H={h}：'+('逐片连续状态' if flow else '资源排程'),y=.97,fontsize=15)
    fig.text(.12,.89,f'Cmax全局最优（完整证据链核验） | 产品回片 Cmax={cmax:g} s | 求解器种子1',fontsize=10)
    legend=fig.legend(handles=[Patch(facecolor=v,label=k) for k,v in colors.items()],loc='lower center',
                      bbox_to_anchor=(.52,.075),ncol=3,frameon=False,fontsize=8)
    note='每行从首次取片到回片连续；非加工驻留含等待及旋转，取放交接计入机械手持片。' if flow else '完整时域含末端清洁；虚线为产品回片边界。机械手仅绘制显式取放，空白不等于全部空闲。'
    fig.text(.12,.035,note,fontsize=9)
    fig.text(.12,.008,'仅认证产品回片Cmax最优，不声称等待时间或末端清洁完成时间最优。',fontsize=9)
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    require(not ax.xaxis.label.get_window_extent(renderer).overlaps(legend.get_window_extent(renderer)),'Axis/legend overlap')
    stem='wafer_flow' if flow else 'resources'
    for ext in ('svg','png','pdf'):fig.savefig(output/f'{stem}.{ext}',dpi=220,facecolor='white')
    plt.close(fig)
    return dict(stem=stem,intervals=len(rows),horizon=horizon)


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--proof',required=True);parser.add_argument('--output',required=True)
    a=parser.parse_args();proof=Path(a.proof).resolve();output=Path(a.output).resolve()
    require(output.is_relative_to(ROOT/'JMS-version/figures') and output!=ROOT/'JMS-version/figures','Use an isolated figures subdirectory')
    data,certificate=checked_data(proof)
    output.mkdir(parents=True,exist_ok=False)
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'svg.fonttype':'none','font.size':10})
    figures=[draw(data,output),draw(data,output,flow=True)]
    dump(output/'manifest.json',dict(proof=str(proof),proof_sha256=digest(proof),renderer_sha256=digest(Path(__file__)),
         original_objective_globally_optimal=True,cmax=certificate['cmax'],figures=figures,
         artifacts={path.name:digest(path) for path in output.iterdir() if path.is_file()}))
    print('CERTIFIED FIGURES WRITTEN '+str(output),flush=True)


if __name__=='__main__':main()
