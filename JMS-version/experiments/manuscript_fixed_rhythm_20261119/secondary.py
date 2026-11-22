"""Certify the physical second objective, reusing the exact first-stage handoff."""
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'manuscript_certified_gaps_20261119'))
from design import EPS, LEVELS, OUT as PRIMARY, RESULTS, ROOT, SEED, TRAINING_SEED, read, rel, save, sha, sparse, witness
sys.path.insert(0,str(HERE.parent/'gap_both_stages_20261118'))
from gap_two_stage import f, finite, gap_certificate, stage_record

OUT=RESULTS/'manuscript_certified_gaps_physicalB_20261119_r2'


def worker(case,arm,a,b,dest,attempt):
    import importlib
    import psutil
    base=read(PRIMARY/'protocol.json')['cases'][case]
    sys.path.insert(0,str(f.BACKENDS[base['backend']]))
    sys.path.insert(1,str(ROOT))
    backend=importlib.import_module('model')
    from validate import validate
    from scip_imports import scip
    started=time.monotonic()
    parent=PRIMARY/'runs'/case/arm/('A_'+a)
    first=read(parent/'evidence.json')
    stage=first['record']
    gate=gap_certificate(stage,LEVELS[a])
    source=parent/'assignment.json.gz'
    if not (first['valid'] and first['phase']=='A' and first['scope']=='global_product_Cmax' and
            first['case']==case and first['arm']==arm and first['threshold']==LEVELS[a] and
            gate['accepted'] and first['gate']['accepted'] and sha(source)==first['assignment_sha256']):
        raise ValueError('Missing certified full-domain first-stage handoff')
    save(dest/'progress.json',dict(phase='build',source=rel(source)))
    x=backend.Integrated(backend.Config(**base['config']))
    m=x.model
    m.hideOutput()
    m.setLogfile(str(attempt/'scip.log'))
    m.setIntParam('parallel/maxnthreads',1)
    m.setIntParam('lp/threads',1)
    m.setIntParam('randomization/randomseedshift',SEED)
    m.setIntParam('timing/clocktype',2)
    m.setRealParam('limits/memory',base['scip_memory_mib'])
    m.setRealParam('limits/time',m.infinity())
    m.setRealParam('limits/gap',LEVELS[b])
    m.setRealParam('limits/absgap',0.)
    variables=m.getVars(transformed=False)
    vals=witness(source,variables)
    def make_sol(values):
        sol=m.createSol()
        for v in variables: m.setSolVal(sol,v,values[v.name])
        return sol
    def checked(sol):
        if not m.checkSol(sol,completely=True,original=True,printreason=True):
            raise ValueError('Full row check failed')
        data=x.result(solution=sol)
        check=validate(data)
        if not check['valid']: raise ValueError(str(check['errors'][:5]))
        data.update(original_model_check=True,validation=check)
        return data,f.physical_metrics(data)
    s=make_sol(vals)
    _,initial=checked(s)
    if abs(initial['cmax']-first['metrics']['cmax'])>EPS: raise ValueError('Handoff makespan mismatch')
    m.freeSol(s)
    for v in variables:
        if v.vtype()!='CONTINUOUS' and not v.name.startswith('sync_'):
            binary=round(vals[v.name])
            m.chgVarLb(v,binary)
            m.chgVarUb(v,binary)
    m.addCons(x.cmax<=initial['cmax']+1e-6,name='certified_handoff_cap')
    by_name={v.name:v for v in variables}
    active=[]
    for chamber in x.cfg.chambers:
        for q in range(2,x.Q):
            if vals[x.keep[chamber,q].name]>.5 and vals[x.keep[chamber,q-1].name]>.5:
                d=by_name[f'rhythm_{chamber}_{q}']
                delta=vals[x.cy.start[chamber,q].name]-2*vals[x.cy.start[chamber,q-1].name]+vals[x.cy.start[chamber,q-2].name]
                vals[d.name]=abs(delta)
                active.append(d)
    if len(active)!=initial['rhythm_centers']: raise ValueError('Frozen structure disagrees with physical pitch centers')
    # For inactive centers, original big-M epigraph rows still apply. Preserve their
    # witness values, but give them zero physical objective weight.
    objective=scip.quicksum(x.waits)+10*x.max_wait+25*scip.quicksum(active)
    m.setObjective(objective,'minimize')
    s=make_sol(vals)
    m.setSolVal(s,x.cmax,initial['cmax'])
    m.setSolVal(s,x.max_wait,initial['wait_max'])
    if not m.checkSol(s,completely=True,original=True,printreason=True) or abs(m.getSolVal(s,objective)-initial['secondary'])>EPS or abs(m.getSolObjVal(s)-initial['secondary'])>EPS:
        raise ValueError('Physical objective failed on stage-A witness')
    m.addSol(s)
    checkpoints=dest/'checkpoints'
    old=sorted(checkpoints.glob('*/check.json'),reverse=True)
    if old:
        entry=read(old[0])
        path=old[0].parent/'values.json.gz'
        if entry['input']!=first['assignment_sha256'] or sha(path)!=entry['sha256']: raise ValueError('Changed B checkpoint')
        s=make_sol(witness(path,variables))
        if not m.checkSol(s,original=True,completely=True): raise ValueError('Restart witness rejected')
        m.addSol(s)
        if entry['lower'] is not None: m.addCons(objective>=entry['lower']-1e-6)
    class Observer(scip.Eventhdlr):
        mask=scip.SCIP_EVENTTYPE.BESTSOLFOUND|scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED|scip.SCIP_EVENTTYPE.NODESOLVED
        last=last_save=0.
        def eventinit(self): self.model.catchEvent(self.mask,self)
        def eventexit(self): self.model.dropEvent(self.mask,self)
        def eventexec(self,event):
            now=time.monotonic()
            if now-self.last<4: return
            self.last=now
            lo,up=finite(m.getDualbound()),finite(m.getPrimalbound())
            save(dest/'progress.json',dict(phase='B',lower=lo,upper=up,gap=finite(m.getGap()),nodes=m.getNNodes()))
            if now-started>60 and now-self.last_save>120 and lo is not None and up is not None and m.getNSols():
                self.last_save=now
                best=m.getBestSol()
                cp=checkpoints/str(time.time_ns())
                path=cp/'values.json.gz'
                save(path,sparse({v.name:m.getSolVal(best,v) for v in variables}))
                save(cp/'check.json',dict(input=first['assignment_sha256'],lower=lo,sha256=sha(path)))
                for stale in sorted(checkpoints.glob('*/check.json'))[:-2]:
                    stale.unlink()
                    (stale.parent/'values.json.gz').unlink()
                    stale.parent.rmdir()
            if psutil.virtual_memory().available<2*1024**3: m.interruptSolve()
    m.includeEventhdlr(Observer(),'B_progress','physical objective and checkpoint')
    save(dest/'progress.json',dict(phase='B',active_centers=len(active),initial=initial))
    m.optimize()
    rec=stage_record(m,'secondary',None)
    cert=gap_certificate(rec,LEVELS[b])
    save(attempt/'termination.json',dict(record=rec,gate=cert))
    if not cert['accepted'] or cert['recomputed_gap'] is None or cert['recomputed_gap']>LEVELS[b]+1e-9:
        raise RuntimeError('Uncertified B '+rec['status'])
    best=m.getBestSol()
    values={v.name:m.getSolVal(best,v) for v in variables}
    m.freeTransform()
    data,physical=checked(make_sol(values))
    if abs(physical['secondary']-rec['primal_bound'])>EPS or physical['cmax']>initial['cmax']+EPS or physical['secondary']>initial['secondary']+EPS:
        raise ValueError('Physical objective, cap or dominance mismatch')
    save(dest/'schedule.json',data)
    save(dest/'assignment.json.gz',sparse(values))
    save(dest/'evidence.json',dict(valid=True,case=case,arm=arm,phase='B',scope='fixed_structure_secondary',
        physical_objective='sum_wait+10*max_wait+25*sum_pitch_over_frozen_active_centers',active_centers=[v.name for v in active],
        source=rel(source),input_sha256=first['assignment_sha256'],primary_evidence_sha256=sha(parent/'evidence.json'),
        assignment_sha256=sha(dest/'assignment.json.gz'),schedule_sha256=sha(dest/'schedule.json'),
        threshold=LEVELS[b],solver_seed=SEED,training_seed=TRAINING_SEED,initial=initial,input_metrics=initial,
        metrics=physical,record=rec,gate=cert,elapsed=time.monotonic()-started,attempt=attempt.name))
