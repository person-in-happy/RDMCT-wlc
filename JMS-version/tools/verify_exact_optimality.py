"""Verify the full proof chain before certifying the original Cmax optimum."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,math,sys
from ortools.sat import cp_model_pb2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from model import Config
from validate import validate,TOL
from run_experiments import assets,digest,dump
from optimality_runtime import certificate_asset_changes
from incumbent_sublevel import capacity_certificate
from terminal_cleanup_bound import cleanup_certificate


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def require(condition,message):
    if not condition:raise ValueError(message)


def verify(search,original_certificate):
    search=Path(search).resolve();original_certificate=Path(original_certificate).resolve()
    manifest=read(search/'manifest.json');result=read(search/'result.json');finished=read(search/'finished.json')
    require(manifest['ortools']=='9.14.6206','Unreviewed solver version')
    certificate_asset_changes(manifest['assets'],assets())
    for name,sha in manifest['scripts'].items():
        require(digest(search/name)==sha and digest(Path(__file__).with_name(name))==sha,'Unreviewed or changed proof code: '+name)
    for name,key in (('model.pb','cp_model_sha256'),('response.pb','cp_response_sha256')):
        require(digest(search/name)==manifest[key],'Solver artifact hash mismatch: '+name)
    response=cp_model_pb2.CpSolverResponse();response.ParseFromString((search/'response.pb').read_bytes())
    model=cp_model_pb2.CpModelProto();model.ParseFromString((search/'model.pb').read_bytes())
    require(response.status==cp_model_pb2.OPTIMAL,'CP response is not OPTIMAL')
    require(result['primary_status']=='optimal' and finished['sublevel_optimal'],'Primary solve not optimal')
    require(result.get('sublevel_model_check') is True,'Original exported MILP rows failed')
    physical=validate(result);require(physical['valid'],'Final physical replay failed')
    upper=physical['product_return_cmax']
    for value in (response.objective_value,response.best_objective_bound,result['primary_bound'],result['cmax']):
        require(math.isfinite(value) and abs(value-upper)<=TOL,'Primary bounds not closed')
    require(abs(result['primary_gap'])<=1e-6,'Nonzero reported gap')
    values=read(search/'variables.json')['values']
    require(len(response.solution)==len(model.variables),'Incomplete solver assignment')
    require(values=={v.name:response.solution[i] for i,v in enumerate(model.variables)},'Saved assignment differs from solver response')
    source=Path(manifest['source']);initial=Path(manifest['certificate'])
    require(digest(source)==manifest['source_sha256'] and digest(initial)==manifest['certificate_sha256'],'Initial witness changed')
    initial_cert=read(initial)
    require(initial_cert['accepted'] and initial_cert['full_candidate_space'] and initial_cert['source_sha256']==digest(source),'Invalid initial original-model certificate')
    certificate_asset_changes(initial_cert['assets'],assets())
    source_data=read(source);source_physical=validate(source_data)
    require(source_physical['valid'],'Initial witness physical replay failed')
    cfg=Config(**manifest['config'])
    require(not cfg.max_pairs and not cfg.max_cycles,'Original configuration was capacity restricted')
    require(result['config']==manifest['config']==source_data['config'],'Configuration drift')
    capacity=capacity_certificate(cfg,round(source_physical['product_return_cmax']))
    cleanup=cleanup_certificate(cfg,round(source_physical['product_return_cmax']),capacity)
    require(capacity==manifest['capacity_certificate']==result['capacity_certificate'],'Capacity certificate mismatch')
    require(cleanup==manifest['cleanup_certificate']==result['cleanup_certificate'],'Cleanup certificate mismatch')
    audit=read(search/'integer_export_audit.json')
    require(audit==result['integer_timing_audit'],'Timing audit changed')
    require(audit['constraints']==len(model.constraints) and audit['variables']==len(model.variables),'Incomplete linear export')
    require(sum(audit[k] for k in ('physical_difference_rows','derived_helper_rows','integer_only_rows'))==audit['constraints'],'Unclassified exported row')
    final=read(original_certificate)
    require(final['accepted'] and final['full_candidate_space'],'Final full-model feasibility not certified')
    require(final['source_sha256']==digest(search/'result.json'),'Final full-model certificate is for another result')
    certificate_asset_changes(final['assets'],assets())
    completion=read(original_certificate.parent/'completion.json');replay=validate(completion)
    require(completion['config']==result['config'] and replay['valid'],'Original model completion failed replay')
    require(abs(replay['product_return_cmax']-upper)<=TOL,'Full-model completion changed Cmax')
    return dict(schema=1,certified_utc=datetime.now(timezone.utc).isoformat(),
        original_objective_globally_optimal=True,objective='product-return Cmax',cmax=upper,
        search=str(search),result_sha256=digest(search/'result.json'),manifest_sha256=digest(search/'manifest.json'),
        original_certificate=str(original_certificate),original_certificate_sha256=digest(original_certificate),
        physical=physical,capacity_theorem=capacity['theorem'],cleanup_theorem=cleanup['theorem'],
        integer_timing_theorem=audit['theorem'],label_symmetry_theorem='anonymous_pair_and_dummy_label_permutation_v1',
        solver_response_sha256=digest(search/'response.pb'),scope='Primary optimum; no secondary waiting optimality claim')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--search',required=True)
    p.add_argument('--original-certificate',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();certificate=verify(a.search,a.original_certificate)
    output=Path(a.output);require(not output.exists(),'Preserve existing proof certificate');dump(output,certificate)
    print('ORIGINAL OBJECTIVE CERTIFIED Cmax='+str(certificate['cmax']),flush=True)


if __name__=='__main__':main()
