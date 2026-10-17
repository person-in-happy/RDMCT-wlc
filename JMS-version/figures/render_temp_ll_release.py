"""Render temp schedules with explicit LL reset identity and a single full-horizon panel.
Uses the current manifest and immutable solutions; never changes event times.
"""
from pathlib import Path
import sys, json, re, hashlib, shutil, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
import petri_gantt
import gantt_build as g
from cie.code.analyze_cie_solutions import _parse_solution
OUT=ROOT/'JMS-version/figures/temp'
RESET='#D6C6E3'; EMPTY='#64748B'; SETUP='#C7DDEB'

def prepare(row):
    path=Path(row['source_solution'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['solution_sha256'], path
    v=_parse_solution(path); schedule=petri_gantt._collect_resource_schedule(v)
    raw=schedule['tasks']; tasks=[]
    for t in raw:
        if t['color'].upper()=='#2A9D8F': continue
        color=t['color'].upper()
        if 'reset' in t['label'].lower() and t['lane'].startswith('LL'): color=RESET
        elif 'empty' in t['label'].lower() and t['lane'].endswith('robot'): color=EMPTY
        tasks.append(g.Task(t['lane'],t['start'],t['end'],color,0))
    for k,value in v.items():
        m=re.fullmatch(r'clean_active_(\d+)_(\d+)',k)
        if m and value>.5:
            c,e=m.groups(); suffix=f'{c}_{e}'
            a,b=v[f'clean_start_{suffix}'],v[f'clean_end_{suffix}']
            assert abs(b-a-500)<1e-5
            for start,end,col in [(v[f'clean_front_load_start_{suffix}'],a,SETUP),(a,b,'#2A9D8F'),(b,v[f'clean_front_unload_end_{suffix}'],SETUP)]:
                if end-start>1e-6: tasks.append(g.Task(f'CH{c} PM',start,end,col,0))
    tasks=list(dict.fromkeys(tasks))
    resets=[t for t in raw if t['lane'].startswith('LLupper') and 'vent reset' in t['label']]
    for r in resets:
        assert any(t['lane']==r['lane'] and 'VTR pickup' in t['label'] and abs(t['end']-r['start'])<1e-5 for t in raw)
    reset=min(resets,key=lambda t:t['start'])
    reset_time=reset['start']
    overlap=[t for t in raw if t['lane']=='VTR robot' and min(t['end'],reset['end'])-max(t['start'],reset_time)>1e-5]
    assert overlap, row['suite']
    expected=90 if row['suite'].endswith('pure22') else 180
    process=[t for t in tasks if t.lane.startswith('CH') and t.source_color=='#E45756']
    assert all(abs(t.end-t.start-expected)<1e-5 for t in process)
    for p in process:
        for t in tasks:
            if p.lane==t.lane and t.source_color in ('#BAB0AC','#F2A09A','#2A9D8F',SETUP):
                assert min(t.end,p.end)-max(t.start,p.start)<1e-5,(p,t)
    if expected==90:
        assert all(abs(t.end-t.start-4)<1e-5 for t in tasks if t.lane.startswith('CH') and t.source_color=='#BAB0AC')
    return tasks,schedule['lanes'],reset,{'suite':row['suite'],'solution_sha256':row['solution_sha256'],'upper_reset_count':len(resets),'immediate_reset_verified':True,'detail_reset':reset,'concurrent_vtr_actions':overlap,'process_duration':expected,'cmax':row['metrics']['cmax'],'full_horizon':max(t.end for t in tasks)}

def draw(ax,tasks,lanes,start,end,lang):
    g.draw_gantt(ax,[t for t in tasks if t.lane in lanes],lanes,start,end,lang)
    for t in tasks:
        if t.lane in lanes and t.source_color==RESET and t.end>start and t.start<end:
            ax.barh(len(lanes)-1-lanes.index(t.lane),min(end,t.end)-max(start,t.start),left=max(start,t.start),height=.62,facecolor='none',edgecolor='#886A9A',linewidth=.25,hatch='////')
    ax.tick_params(labelsize=8)
    ax.set_xlabel('时间 / s' if lang=='cn' else 'Time / s',fontsize=9)

def render(row,tasks,lanes,reset,audit,lang,suffix=""):
    n=int(re.search(r'n(\d+)',row['suite'])[1]); h=int(re.search(r'clean(\d+)',row['suite'])[1]); mode='22' if row['suite'].endswith('pure22') else '41'
    g.configure(lang)
    g.COLOR_MAP.update({RESET:RESET,EMPTY:EMPTY,SETUP:SETUP})
    fig=plt.figure(figsize=(10,5.3))
    ax=fig.add_axes([.17,.33,.80,.54])
    cmax=audit['cmax']; horizon=cmax
    draw(ax,tasks,lanes,0,horizon,lang)
    ax.axvline(cmax,color='#222222',ls=(0,(3,2)),lw=.8)
    ax.text(cmax,len(lanes)-.35,f'Cmax = {cmax:.0f} s',ha='right',va='bottom',fontsize=8)
    desc=('纯2×2；允许等待' if n==24 else '纯2×2；链内相邻加工间隔4 s') if mode=='22' else '纯4×1'
    if lang=='en': desc=('Pure 2x2; waiting allowed' if n==24 else 'Pure 2x2; within-chain processing gap 4 s') if mode=='22' else 'Pure 4x1'
    if suffix=='_4s': desc='纯2×2；链内相邻加工间隔固定4 s' if lang=='cn' else 'Pure 2x2; within-chain processing gaps fixed at 4 s'
    fig.suptitle(f'{n}'+('片晶圆' if lang=='cn' else ' wafers')+f' | H={h} | {desc}',fontsize=12,y=.97)
    wph=3600*n/cmax
    fig.text(.57,.235,f'Cmax {cmax:.0f} s | WPH {wph:.2f} | '+(('图示时域 ' if lang=='cn' else 'Displayed horizon ')+f'{horizon:.0f} s'),ha='center',fontsize=9)
    styles=[]
    for source,col,en,cn in g.ACTION_STYLE:
        if source=='#BAB0AC': en,cn='Chamber exchange / rotation','腔室交换/旋转'
        if source=='#2A9D8F': en,cn='Cleaning process (500 s)','清洁处理（500 s）'
        if any(t.source_color==source for t in tasks):styles.append(Patch(facecolor=col,label=cn if lang=='cn' else en))
    styles.extend([Patch(facecolor=RESET,edgecolor='#886A9A',hatch='////',label='LL压力复位' if lang=='cn' else 'LL pressure reset'),Patch(facecolor=EMPTY,label='机器人空载移位' if lang=='cn' else 'Robot empty movement')])
    if any(t.source_color==SETUP for t in tasks): styles.append(Patch(facecolor=SETUP,label='清洁准备/卸片' if lang=='cn' else 'Cleaning setup / unloading'))
    fig.legend(handles=styles,loc='lower center',bbox_to_anchor=(.53,.009),ncol=4,fontsize=7.3,frameon=False,columnspacing=1.2)
    fig.canvas.draw()
    # Ensure panel and legend boxes do not collide.
    renderer=fig.canvas.get_renderer()
    assert not ax.get_tightbbox(renderer).overlaps(fig.legends[0].get_window_extent(renderer))
    dest=OUT if lang=='cn' else OUT/'en'; stem=f'fig_resource_gantt_cleanH{h}_w{n}_{mode}_{lang}_nature{suffix}'
    for ext in ['pdf','svg','png','tiff']: fig.savefig(dest/f'{stem}.{ext}',dpi=400)
    plt.close(fig)

def main():
    manifest=json.loads((OUT/'manifest.json').read_text('utf-8'))
    audits=[]
    for row in manifest:
        tasks,lanes,reset,audit=prepare(row)
        for lang in ['cn','en']:render(row,tasks,lanes,reset,audit,lang)
        audits.append(audit); print(row['suite'],audit['cmax'],flush=True)
    (OUT/'ll_release_layout_checks.json').write_text(json.dumps(audits,indent=2),encoding='utf-8')
    lines=['# 8片与24片补充甘特图','','每个批量包含 H=3、H=10 下纯4×1和纯2×2四张图；中英文各8张，格式为 PDF、SVG、PNG、TIFF。英文位于 en/。','','24片纯2×2恢复为允许等待的已验解排程；8片纯2×2保留连续4 s交换排程。所有时刻来自 manifest.json 指定的解，不通过平移图形修改时序。','','- 每张图仅保留资源时序面板，无局部放大；图示截至产品回片 Cmax，其后的末端清洁保留在原始解与时域记录中。','- 紫色斜线表示压力复位，蓝灰色表示机器人空载移位。','- 复位从模型记录的取片完成时刻立即开始，可与后续VTR动作重叠。','- 当前4 s取放动作未细分内部取片、移动及放片时刻；本图不推断更早的内部释放事件。','- 腔室灰色块表示交换或旋转，浅粉色表示等待，绿色表示500 s清洁处理。','','|批量|H|模式|Cmax / s|图示时域 / s|原始求解状态|','|---:|---:|---|---:|---:|---|']
    for row,a in zip(manifest,audits):
        n=int(re.search(r'n(\d+)',row['suite'])[1]); h=int(re.search(r'clean(\d+)',row['suite'])[1]);mode='2×2' if row['suite'].endswith('pure22') else '4×1'
        lines.append(f"|{n}|{h}|{mode}|{a['cmax']:.0f}|{a['full_horizon']:.0f}|{row['status']}|")
    lines+=['','来源及哈希见 manifest.json；本次取片—复位衔接、并行动作及绘图检查见 ll_release_layout_checks.json。状态沿用原始结果，不把必要条件松弛结果当作完整模型的求解证书。','重绘脚本：../render_temp_ll_release.py。']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':main()
