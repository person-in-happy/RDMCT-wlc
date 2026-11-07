"""Freeze/plan and warm-start checks with optimize explicitly disabled."""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import hashlib,json,sys,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'JMS-version/experiments/nondecreasing_followup_20261102'))
import followup as follow
import followup_models as fm
import strengthen_models as sm
import review_experiments as review
sys.path.insert(0,str(ROOT/'JMS-version/experiments/nondecreasing_strengthening_20261102'))
import strengthen
from evidence_supplement import matrix,defaults

DEST=ROOT/'JMS-version/revisions/20261102_nondecreasing_release/entry_checks'/str(time.time_ns())
DEST.mkdir(parents=True)
checks=[]
class NoOptimize(fm.REAL_MODEL):
    def optimize(self,*a,**k):raise AssertionError('No optimization allowed in entry checks')
class WaferNoOptimize(fm.WaferModel):
    def optimize(self,*a,**k):raise AssertionError('No optimization allowed in entry checks')
original_model=fm.scip.Model; original_wafer=fm.WaferModel
fm.scip.Model=NoOptimize;fm.WaferModel=sm.WaferModel=WaferNoOptimize
try:
    for suite,total in [('paper',102),('qualification',6),('paper_cuts',72),('rhythm',48),('crossover',216)]:
        cases,pairs=matrix(suite)
        assert len(set(pairs))==len(pairs)
        assert len(pairs)*len(defaults(suite)['seeds'])==total
        checks.append(dict(check='main_matrix',suite=suite,cells=total))
    for suite,count in [('timing',72),('parallel',3),('exact',24),('residency',6)]:
        cells=fm.plan(suite);assert len(cells)==len({c['id'] for c in cells})==count
        args=SimpleNamespace(suite=suite,repeats=6,time_limit=None,stage2_limit=60,memory_mb=None,process_memory_mb=None,wall_limit=1800)
        out=DEST/suite;follow.prepare(args,out);spec=follow.checked(out)
        assert spec['release_order_rule']=='global_pjob_index_nondecreasing_lp_pickup'
        assert follow.summarize(out)['pending']==count
        if suite=='timing':
            for case in {c['case'] for c in cells}:
                first=[c['arm'] for i,c in enumerate(cells) if c['case']==case and i%2==0]
                assert Counter(first)=={'pjob':3,'wafer':3}
        for c in cells:
            if c['kind'] in ('reference','parallel'):
                seed=fm.construct(fm.backend.Config(**c['config']),balanced=True)
                assert fm.validate(seed)['valid']
        checks.append(dict(check='followup_freeze',suite=suite,cells=count))
    for driver,suite,count in [(review,'baseline',36),(review,'rhythm',24),(review,'cleanup',42),(strengthen,'representation',36),(strengthen,'rhythm_memory',12)]:
        args=SimpleNamespace(suite=suite,seeds=[1,2,3],time_limit=300,stage2_limit=60,cleanup_limit=60,memory_mb=6000,process_memory_mb=7000,wall_limit=3600)
        out=DEST/suite;args.campaign=str(out)
        # Exercise preparation in the dedicated verification directory only.
        # The public command keeps its original results-directory guard.
        resolve=driver.resolve_campaign
        driver.resolve_campaign=lambda value: out
        try: driver.prepare(args)
        finally: driver.resolve_campaign=resolve
        spec=driver.checked(out)
        assert len(spec['cells'])==count
        assert spec['release_order_rule']=='global_pjob_index_nondecreasing_lp_pickup'
        checks.append(dict(check='supplement_freeze',suite=suite,cells=count))
    for recipe in ('4x1','mixed'):
        for arm in ('pjob','wafer'):
            cell=next(c for c in fm.plan('timing') if c['case']==f'n8_H5_{recipe}_dual' and c['arm']==arm)
            out=DEST/f'warm_{recipe}_{arm}';out.mkdir()
            result=fm.run_cell(cell,out,{},DEST)
            assert result['valid'] and not result['solver_started']
            source=fm.read(cell['source']); replay=fm.read(out/'result.json')
            for field in ('events','jobs','pairs','cycles'):
                assert sm.same_replay(source[field],replay[field]),field
            checks.append(dict(check='historical_start_full_model_and_replay',case=cell['case'],arm=arm,dimensions=result['dimensions']))
finally:
    fm.scip.Model=original_model;fm.WaferModel=sm.WaferModel=original_wafer
baseline=json.loads((ROOT/'JMS-version/revisions/20261102_nondecreasing_release/original_code_hashes.json').read_text('utf-8'))
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in baseline.items())
receipt=dict(passed=len(checks),failed=0,optimization_calls=0,formal_campaigns_started=0,directory=str(DEST),checks=checks,original_files_unchanged=len(baseline),implementation_hashes=follow.inventory()|strengthen.inventory()|review.inventory())
fm.dump(DEST/'validation.json',receipt)
fm.dump(HERE/'entry_validation.json',receipt)
print(json.dumps({k:receipt[k] for k in ('passed','failed','optimization_calls','original_files_unchanged','directory')}),flush=True)
