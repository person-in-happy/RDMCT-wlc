"""Read-only generated-order audit; does not equate unfixed bounds with freedom."""
from pathlib import Path
from itertools import combinations
import json,re,sys
from model import Config,Integrated
from run_experiments import dump,digest
ROOT=Path(__file__).resolve().parents[1]
records=[]
for mode in ['4x1','2x2']:
 source=ROOT/'results/joint_model/mode_endpoints_v1/runs'/f'n16_H10_{mode}_dual_s1_scip_joint'
 raw=json.loads((source/'result.json').read_text());x=Integrated(Config(**raw['config']));m=x.model
 saved=json.loads((source/'build.json').read_text())['dimensions'];assert m.getNVars()==saved['variables'] and m.getNConss()==saved['constraints']
 vars={v.name:v for v in m.getVars(transformed=False)};groups={};seen=set()
 for robot,events in x.robots.items():
  stats=dict(generated=0,bound_fixed=0,route_direct=0,route_transitive=0)
  for a,b in combinations(events,2):
   name=f'order_{a["name"]}_{b["name"]}';assert name in vars;seen.add(name);stats['generated']+=1
   v=vars[name];stats['bound_fixed']+=int(v.getLbGlobal()==v.getUbGlobal())
   if a.get('job') is not None and a.get('job')==b.get('job'):
    direct={frozenset(z) for z in [('origin_pick','al_put'),('al_put','al_pick'),('al_pick','upper_put'),('lower_pick','origin_put')]}
    stats['route_direct' if frozenset((a['kind'],b['kind'])) in direct else 'route_transitive']+=1
   elif a.get('pair') is not None and a.get('pair')==b.get('pair'):stats['route_direct']+=1
  stats['unclassified']=stats['generated']-stats['route_direct']-stats['route_transitive'];groups[robot]=stats
 for group,prefix in [('AL','order_AL_'),('LL_U','order_U_'),('LL_L','order_L_'),('shared_dummy','order_identity_')]:
  vs=[v for n,v in vars.items() if n.startswith(prefix)];seen.update(v.name for v in vs)
  groups[group]=dict(generated=len(vs),bound_fixed=sum(v.getLbGlobal()==v.getUbGlobal() for v in vs),route_direct=0,route_transitive=0,unclassified=len(vs))
 for c in [2,3]:groups['CH'+str(c)]=dict(generated=0,note='Cycle occupancy/front/first/last encode chamber order; no pairwise CH order family.')
 rest=[n for n in vars if n.startswith('order_') and n not in seen];assert not rest,rest[:10]
 log=(source/'solver.log').read_text(errors='replace')
 summaries=re.findall(r'presolved problem has[^\n]+',log)
 records.append(dict(mode=mode,source=str(source),source_sha256=digest(source/'result.json'),dimensions=saved,candidate_pairs=x.P,candidate_cycles_per_chamber=x.Q,groups=groups,presolve_summaries=summaries,root_lp_timeout='LP solver hit time limit' in log,interpretation='Route counts are valid conditional on activation; remaining candidates are not proven free. Presolve entries include initialization phases; final entry refers to main solve.'))
 m.freeProb()
out=ROOT/'results/joint_model_validation/order_audit_n16_H10_20260920';out.mkdir(parents=True,exist_ok=True);dump(out/'audit.json',records)
for r in records:print(json.dumps(r))
