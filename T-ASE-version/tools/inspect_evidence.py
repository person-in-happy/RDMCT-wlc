from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
for suite,budget in [('main',600),('stability',600),('doe',600),('spbs',600),('sensitivity',600),('ood',1200)]:
 mem=4096 if suite=='ood' else 2048
 p=ROOT/f'cie/results/{suite}/cie_{suite}_{budget}s_mem{mem}_repro_v1/submission_analysis/submission_audit.json'
 d=json.loads(p.read_text('utf-8-sig'))
 print(suite,{k:d.get(k) for k in ['expected_rows','csv_rows','incumbent_rows','ok','issues']})
lp=ROOT/'cie/data/core/spbs/cie_core_n016_f000_m016_proc100.lp'
s=lp.read_text('utf-8')
print('Frozen core LP c_max lines:\n'+'\n'.join(l for l in s.splitlines() if 'c_max' in l)[:4200])

