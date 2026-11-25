"""Prepare a verified full-product starting order and variants with two four-wafer cycles per chamber."""
import sys
from physical import SOURCE,CFG,HERE,JMS,BASE,load,save,sha,STEPS
from native16 import to_slots

def prepare():
    src=JMS/'results/sublevel_projection_20261120_r1/D_n16_4x1/complete/schedule.json'
    raw=load(src);out=JMS/'results/table3_pure16_active_20261125/plans';out.mkdir(exist_ok=True,parents=True)
    slots=to_slots(raw,'4x1');events={(e.get('job'),e['kind']):e['start'] for e in raw['events'] if 'job' in e}
    for i,w in enumerate(sorted([w for w in raw['jobs'] if w['product']],key=lambda w:w['pjob_index'])):
        for n in STEPS:slots[f'{i}_{n}']=int(w[n+'_start'] if n in ('load','unload') else events[w['name'],n])
    slots['makespan']=int(raw['cmax']);save(out/'reference920.json',slots)
    return out

if __name__=='__main__':prepare()
