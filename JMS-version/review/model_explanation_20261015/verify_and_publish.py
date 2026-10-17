from pathlib import Path
import math, json, shutil, hashlib
import pymupdf

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
report=json.loads((HERE/'build_report.json').read_text())
assert not report['compile_issues']
assert hashlib.sha256((PAPER/'JMS_Review_CN.tex').read_bytes()).hexdigest()==report['source_sha256']
original=PAPER/'results/joint_model/structure_check_20261011_203359/matched_n4_H10_mixed_dual/scip_fixed/result.json'
alternative=PAPER/'results/joint_model/auxiliary_partition_retry_20261013_103715/result.json'
a=json.loads(original.read_text()); b=json.loads(alternative.read_text())
assert a['status']=='optimal' and a['validation']['valid'] and b['validation']['valid']
assert round(a['cmax'])==532 and round(b['cmax'])==403
assert [round(j['loan_end']) for j in a['jobs'] if j['product']]==[525,532,511,504]
assert [(round(c['start']),round(c['end'])) for c in a['cycles']]==[(302,482),(104,194),(204,294)]
events={e['name']:e for e in a['events']}
for name,interval in {'origin_pick':(0,4),'al_put':(7,11),'al_pick':(31,35),
    'upper_put':(66,70),'source_pick':(100,101),'destination_put':(308,309),
    'lower_pick':(459,463),'origin_put':(507,511)}.items():
    e=events['LP3_W1_'+name]
    assert (round(e['start']),round(e['end']))==interval
audit=json.loads((PAPER/'results/joint_model_validation/followup_20261013/audit.json').read_text())
w=audit['auxiliary_witness']
assert w['assignment_satisfies_unrestricted_MILP'] and w['physical_replay']['valid']
assert w['same_config_product_pairing_chambers_and_cycles'] and w['exposure_overlap_seconds']==111
assert round(w['relative_reduction_percent'],2)==24.25
assert (2+2*2, math.floor(6/9),4+6,6)==(6,0,10,6)
assert (math.floor(6/2),4+6+2*3,6+3)==(3,16,9)
assert 15+10*10+25*20==615 and 615+3*2==621
assert round(.725+.25*math.sqrt(2)+.20,4)==1.2786
assert round(.5*math.tanh(.3),4)==.1457
assert round(math.log(.6*.1),4)==-2.8134 and round(math.log(.4*.9),4)==-1.0217
assert math.factorial(8)**2//math.factorial(4)**2==2822400
assert math.factorial(12)**2//math.factorial(6)**2==442597478400
pdf=HERE/'build/MODEL_EXPLANATION_CN.pdf'
doc=pymupdf.open(pdf)
text='\n'.join(p.get_text() for p in doc)
assert len(doc)==32
assert all(f'({i})' in text for i in range(1,43)), 'Missing rendered formula number'
report.update({'saved_example_times_checked':True,'auxiliary_witness_checked':True,
               'key_arithmetic_checked':True,'rendered_formula_numbers':42,
               'visual_review':'All 32 pages reviewed in contact sheets; pages 13, 17 and 25 inspected at full size.'})
(HERE/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
destination=PAPER/'output/pdf/MODEL_EXPLANATION_CN.pdf'
destination.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(pdf,destination)
print(str(destination))
