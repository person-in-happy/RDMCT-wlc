"""Decode a full set of timed projected moves, then independently test its native feasibility."""
from pathlib import Path
import sys
from physical import JMS,CFG,STEPS,make,load,save,sha
from refine import certify

def check(src):
    values=load(src/'projection.json');hint=load(src/'native_hint.json')
    names={w:i for i,w in enumerate(CFG.pjobs[0]['wafers'])}
    dest=JMS/'results/table3_pure16_active_20261125'/'vault_handoff'/src.parent.name/src.name
    slots={};times={};pid=0
    for ch,cycles in hint['cycles'].items():
        c=int(ch)-2
        for q,cy in enumerate(cycles):
            g=c*10+q;slots[f'use{c,q}']=1;times[f'start{c,q}']=values[f'start_{g}']
            bl,fl,fu,bu=[values[f'{act}_{g}'] for act in ('bl','fl','fu','bu')]
            times[f'rot_before_{ch}_{q}']=bl+1;times[f'rot_after_{ch}_{q}']=fu+1
            for s,side in enumerate(('back','front')):
                group=cy[side]
                for w in group:slots[f'w{names[w]}_{c}_{q}_{s}']=1
                times[f'load_{pid}']=fl if s else bl;times[f'unload_{pid}']=fu if s else bu
                for r in range(len(group),2):
                    times[f'w_{pid}_{r}_source_pick']=values[f'vs_in_{g,s}_{r-len(group)}']
                    times[f'w_{pid}_{r}_destination_put']=values[f'vs_out_{g,s}_{r-len(group)}']
                pid+=1
    for w,acts in hint['product_event_hints'].items():
        for act,t in acts.items():slots[f'{names[w]}_{act}']=t;times[f'{names[w]}_{act}']=t
    times['makespan']=values['true_C'];srcplan=dest/'plan.json';save(srcplan,slots)
    m,decode=make(srcplan,int(values['true_C']),10000)
    class Clock:
        def value(self,v):return times[v.name]
    try:data=decode(Clock())
    except (AssertionError,ValueError) as err:
        save(dest/'replay_failure.json',dict(input=sha(src/'projection.json'),error=str(err)));raise
    path=dest/f'schedule_{data["cmax"]}.json';save(path,data)
    certify(data,path)
    print('Native certified',data['cmax'],flush=True)

if __name__=='__main__':check(Path(sys.argv[1]).resolve())
