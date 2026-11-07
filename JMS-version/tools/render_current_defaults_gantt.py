"""Render a verified current-default schedule. Never optimize or infer optimality from a filename."""
from pathlib import Path
from collections import defaultdict
import argparse,json,hashlib,sys,math
ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'JMS-version/model4_pjob_nonprocessing_20261103'
sys.path.insert(0,str(BACKEND))
from model import Config,Integrated
from validate import validate
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

COLORS={'ATR承片/取放':'#4477AA','VTR承片/取放':'#CCBB44','AL驻留/占用':'#AA77AA',
        'LL驻留/槽位占用':'#77AADD','腔内非加工驻留':'#DDDDDD','工艺处理':'#EE8866',
        '腔室装卸/旋转':'#667788','清洁':'#228833'}
def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)

def check(result,variables,proof,require_optimal):
 d=read(result);c=d['config']
 require((c['module_residency'],c['robot_residency'],c['horizon'],c.get('chamber_residency_basis'))==(100,100,10000,'nonprocessing'),'Input does not use current paper defaults')
 physical=validate(d);require(physical['valid'],str(physical['errors']))
 x=Integrated(Config(**c));m=x.model;sol=m.createSol();vals=read(variables)['values']
 try:
  for v in m.getVars(transformed=False):m.setSolVal(sol,v,vals[v.name])
  require(m.checkSol(sol,printreason=False,completely=True,original=True),'Full original-model assignment rejected')
 finally:m.freeSol(sol);m.freeProb()
 certified=False
 if proof:
  cert=read(proof)
  for f,k in [(result,'result_sha256'),(variables,'variables_sha256'),(BACKEND/'model.py','model_sha256'),(BACKEND/'physical_validate.py','validator_sha256')]:require(sha(f)==cert[k],'Certificate hash mismatch: '+str(f))
  oldpath=ROOT/cert['source_result'];old=read(oldpath)
  require(sha(oldpath)==cert['source_result_sha256'],'Source result changed')
  require(sha(ROOT/cert['source_variables'])==cert['source_variables_sha256'],'Source variables changed')
  require(old.get('status')=='optimal' and old.get('original_model_check') is True and old.get('restricted_candidate_bounds') is False,'Uncertified source optimum')
  require(abs(old['dual_bound']-old['cmax'])<2e-4 and abs(old['gap'])<1e-8,'Source bounds not closed')
  oldcfg=old['config'];differences={k for k in set(c)|set(oldcfg) if c.get(k)!=oldcfg.get(k)}
  require(differences=={'module_residency','robot_residency','horizon','chamber_residency_basis'},'Unexpected instance change')
  require(c['module_residency']+max(c['full_time'],2*c['mix_time'],c['cleaning_time'])<=oldcfg['module_residency'] and c['robot_residency']<=oldcfg['robot_residency'] and c['horizon']<=oldcfg['horizon'],'Feasible-set containment not established')
  require(d['candidate_pairs']==old['candidate_pairs'] and d['candidate_cycles']==old['candidate_cycles'],'Candidate domain changed')
  certified=abs(physical['product_return_cmax']-old['dual_bound'])<2e-4
 else:
  bound=d.get('primary_bound',d.get('dual_bound'))
  certified=(d.get('primary_status',d.get('status'))=='optimal' and d.get('full_candidate_space') is True and d.get('restricted_candidate_bounds') is False and isinstance(bound,(int,float)) and math.isfinite(bound) and abs(bound-physical['product_return_cmax'])<2e-4)
 require(not require_optimal or certified,'Only feasible: no full-model Cmax optimum certificate')
 return d,physical,certified

def rows(d):
 ej=defaultdict(dict);jobs={j['name']:j for j in d['jobs']};flows=[];resources=[];slots={'U':[],'L':[]}
 for e in d['events']:
  if 'job' in e:ej[e['job']][e['kind']]=e
  if e['robot']:resources.append((e['robot']+'取放',e['start'],e['end'],e['robot']+'承片/取放'))
  if e['location'].startswith('CH'):resources.append((e['location'],e['start'],e['end'],'腔室装卸/旋转'))
 for j in sorted(d['jobs'],key=lambda j:(not j['product'],j.get('wafer_number',0),j['name'])):
  e=ej[j['name']];label=j.get('encoded_product',j['identity']+' 辅助片')
  if j['product']:label+=' / 晶圆'+str(j['wafer_number'])
  seg=[]
  if 'origin_pick' in e:
   if 'al_put' in e:
    seg += [(e['origin_pick']['start'],e['al_put']['end'],'ATR承片/取放'),(e['al_put']['end'],e['al_pick']['start'],'AL驻留/占用'),(e['al_pick']['start'],e['upper_put']['end'],'ATR承片/取放')]
    resources.append(('AL占用',e['al_put']['start'],e['al_pick']['end'],'AL驻留/占用'))
   else:seg.append((e['origin_pick']['start'],e['upper_put']['end'],'ATR承片/取放'))
   seg.append((e['upper_put']['end'],e['source_pick']['start'],'LL驻留/槽位占用'))
   slots['U'].append((e['upper_put']['start'],e['source_pick']['end']+d['config']['upper_reset']))
   slots['L'].append((e['destination_put']['start'],e['lower_pick']['end']+d['config']['lower_reset']))
  seg.append((e['source_pick']['start'],j['load_end'],'VTR承片/取放'))
  cursor=j['load_end']
  for c in sorted((c for c in d['cycles'] if j['pair'] in c['pairs']),key=lambda c:c['start']):
   seg.extend([(cursor,c['start'],'腔内非加工驻留'),(c['start'],c['end'],'清洁' if c['mode']=='clean' else '工艺处理')]);cursor=c['end']
  seg.extend([(cursor,j['unload_start'],'腔内非加工驻留'),(j['unload_start'],e['destination_put']['end'],'VTR承片/取放')])
  if 'origin_put' in e:seg.extend([(e['destination_put']['end'],e['lower_pick']['start'],'LL驻留/槽位占用'),(e['lower_pick']['start'],e['origin_put']['end'],'ATR承片/取放')])
  cursor=j['loan_start']
  for start,end,kind in seg:
   require(abs(start-cursor)<2e-4 and end>=start-2e-4,'Discontinuous wafer trajectory')
   if end-start>1e-6:flows.append((label,start,end,kind))
   cursor=end
  require(abs(cursor-j['loan_end'])<2e-4,'Incomplete wafer trajectory')
 for key,intervals in slots.items():
  ends=[-1e9,-1e9]
  for start,end in sorted(intervals):
   slot=min(range(2),key=lambda i:ends[i]);require(ends[slot]<=start+2e-4,'LL capacity violation');ends[slot]=end
   resources.append((('上LL' if key=='U' else '下LL')+str(slot+1),start,end,'LL驻留/槽位占用'))
 for c in d['cycles']:resources.append(('CH'+str(c['chamber']),c['start'],c['end'],'清洁' if c['mode']=='clean' else '工艺处理'))
 return flows,list(dict.fromkeys(resources))

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--result',type=Path,required=True);p.add_argument('--variables',type=Path,required=True);p.add_argument('--proof',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-optimal',action='store_true');a=p.parse_args()
 d,v,certified=check(a.result,a.variables,a.proof,a.require_optimal);flow,resource=rows(d)
 dest=a.output.resolve();require(dest.is_relative_to(ROOT/'JMS-version/figures'),'Use an isolated manuscript figures directory');dest.mkdir(parents=True,exist_ok=True)
 from current_defaults_swimlane import draw
 horizon,evidence=draw(d,v,certified,dest);cmax=v['product_return_cmax']
 manifest=dict(result=str(a.result.resolve()),result_sha256=sha(a.result),variables_sha256=sha(a.variables),proof=str(a.proof.resolve()) if a.proof else None,certified_product_cmax=certified,cmax=cmax,resource_horizon=horizon,renderer_sha256=sha(Path(__file__)),swimlane_renderer_sha256=sha(Path(__file__).with_name('current_defaults_swimlane.py')),flow_intervals=len(flow),resource_intervals=len(evidence['bars']),explicit_events_covered=evidence['explicit_events_covered'],complete_wafer_paths=evidence['complete_wafer_paths'],physical=v,notes='Unified resource time lanes and wafer identity labels; no path lines or arrows. Implicit travel is completed immediately before the next handling; alignment/pump/vent immediately after deposit. LL slots are equivalent display assignments. No new optimization.')
 (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
