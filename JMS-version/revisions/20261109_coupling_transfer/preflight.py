"""Non-optimization acceptance checks for the new entry; not experiment data."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'JMS-version/tools'))
import journal_support_experiments as j

OUT = Path(__file__).resolve().parent
checks = []
for suite in ('mechanism', 'chain', 'backfill_standard', 'qualification'):
    out = j.RESULTS / ('journal_support_preflight_20261109_' + suite + '_r2')
    a = SimpleNamespace(suite=suite, source_campaign=None, time_limit=300,
                        wall_limit=2400, min_available_fraction=.10)
    j.prepare(a, out)
    spec = j.checked(out)
    if suite == 'mechanism':
        c = next(c for c in spec['cells'] if c['case']=='n1_2x2_H2_D8' and c['arm']=='optional' and c['seed']==1)
        j.worker(out, c['id'], True)
        source_cell = c
    elif suite == 'chain':
        j.worker(out, spec['cells'][0]['id'], True)
    elif suite == 'qualification':
        try:
            j.parent_sources(str(out), 'qualification')
        except ValueError as e:
            assert 'Finish every parent' in str(e)
        else:
            raise AssertionError('Pending parent was accepted')
    checks.append(dict(suite=suite, campaign=str(out), cells=len(spec['cells']),
                        contract=j.digest(out/'campaign.json'), solver_started=False))

# Check every distinct policy family/ablation and training seed on a real D
# model, but never invoke SCIP.optimize or policy training.
policies = []
for method in ('hem', 'proposed', 'feature_only', 'proposed_no_structure', 'proposed_greedy'):
    for training in (1, 2, 3):
        x = j.base.backend.Integrated(j.base.backend.Config(**j.read(source_cell['config'])))
        try:
            agent, record = j.base.install(x.model, method, training)
            policies.append(dict(method=method, training_seed=training, policy=record, loaded=True))
        finally:
            x.model.freeProb()
        print(f'policy_checks={len(policies)}/15 solver_started=false', flush=True)

# Exercise the new saved shared-input path with an identity preparation stub.
# This explicitly does NOT test SPBS quality or run optimization.
fixture = OUT/'verification/shared_input_identity_fixture'
fixture.mkdir(parents=True, exist_ok=False)
with patch.object(j.base, 'improve_skeleton', side_effect=lambda x, values, budget: (values, [])):
    result = j.shared_spbs_run(source_cell, fixture, dict(time_limit=300, memory_mb=8796093022207.))
assert result['full_model_audit']['valid']
result.update(solver_started=False, fixture_only=True, improvement_function_stubbed=True)
j.dump(fixture/'fixture_check.json', result)

j.dump(OUT/'preflight_checks.json', dict(driver_sha256=j.digest(j.HERE), solver_started=False,
                                       campaigns=checks, policies=policies, shared_input_fixture_valid=True,
                                       pending_parent_rejected=True, actual_optimization_tested=False))
j.dump(OUT/'prospective_instances.json', dict(test27=j.test_cases(), mechanism24=j.mechanism_cases()))
print(json.dumps(dict(solver_started=False, campaigns=len(checks), policies_loaded=len(policies), shared_input_fixture_valid=True)))
