"""Non-solving entry checks. Outputs are isolated from formal campaigns."""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import json
import sys
import time

import followup as driver
import followup_models as fm

ROOT = fm.ROOT
DEST = ROOT / 'JMS-version/revisions/20261102_review_corrections/entry_checks' / str(time.time_ns())
DEST.mkdir(parents=True)
checks = []


class NoOptimize(fm.REAL_MODEL):
    def optimize(self, *args, **kwargs):
        raise AssertionError('Optimization is forbidden in entry checks')


class WaferNoOptimize(fm.WaferModel):
    def optimize(self, *args, **kwargs):
        raise AssertionError('Optimization is forbidden in entry checks')


original_model = fm.scip.Model
original_wafer = fm.WaferModel
fm.scip.Model = NoOptimize
fm.WaferModel = WaferNoOptimize
try:
    for suite, count in [('timing', 72), ('parallel', 3), ('exact', 18), ('residency', 6)]:
        cells = fm.plan(suite)
        assert len(cells) == count and len({c['id'] for c in cells}) == count
        args = SimpleNamespace(suite=suite, repeats=6, time_limit=None, stage2_limit=60,
            memory_mb=None, process_memory_mb=None, wall_limit=1800)
        out = DEST / suite
        driver.prepare(args, out)
        spec = driver.checked(out)
        assert driver.summarize(out)['pending'] == count
        if suite == 'timing':
            for case in {c['case'] for c in cells}:
                first = [c['arm'] for i, c in enumerate(cells) if c['case'] == case and i % 2 == 0]
                assert Counter(first) == {'pjob': 3, 'wafer': 3}
            assert spec['settings']['time_limit'] == 0
        checks.append(dict(check='prepare_and_freeze', suite=suite, cells=count, passed=True))

    old = fm.read(ROOT / 'JMS-version/revisions/20261101_strengthening_update/verified_strengthening.json')
    expected = {(r['case'], r['arm']): r['dimensions'] for r in old['rows'] if r['suite'] == 'representation'}
    for recipe in ('4x1', 'mixed'):
        case = f'n8_H5_{recipe}_dual'
        for arm in ('pjob', 'wafer'):
            cell = next(c for c in fm.plan('timing') if c['case'] == case and c['arm'] == arm)
            dest = DEST / ('check_' + case + '_' + arm)
            dest.mkdir()
            result = fm.run_cell(cell, dest, {}, DEST)
            assert not result['solver_started'] and result['valid']
            assert result['dimensions'] == expected[case, arm]
            source = fm.read(cell['source'])
            final = fm.read(dest / 'result.json')
            from strengthen_models import same_replay
            for field in ('events', 'jobs', 'pairs', 'cycles'):
                assert same_replay(source[field], final[field]), field
            checks.append(dict(check='fair_build_same_dimensions_and_physical_start', case=case, arm=arm, passed=True))

    for cell in fm.plan('parallel'):
        cfg = fm.backend.Config(**cell['config'])
        x = fm.build_fair(cfg, 'pjob')
        try:
            before = x.model.getNConss()
            fm.overlap_constraints(x)
            assert x.model.getNConss() == before + 4
            seed = fm.construct(cfg)
            assert fm.validate(seed)['valid'] and fm.numbers(seed)['production_overlap'] == 0
            checks.append(dict(check='parallel_domain_and_valid_serial_control', case=cell['case'], passed=True))
        finally:
            x.model.freeProb()

    for cell in fm.plan('exact'):
        if cell['kind'] == 'reference':
            cfg = fm.backend.Config(**cell['config'])
            seed = fm.construct(cfg, balanced=True)
            assert fm.validate(seed)['valid']
            checks.append(dict(check='exact_physical_reference', case=cell['case'], passed=True))
finally:
    fm.scip.Model = original_model
    fm.WaferModel = original_wafer

receipt = dict(passed=len(checks), failed=0, optimization_calls=0, directory=str(DEST), checks=checks,
               implementation_hashes=driver.inventory())
fm.dump(DEST / 'validation.json', receipt)
fm.dump(fm.HERE / 'entry_validation.json', receipt)
print(json.dumps(dict(passed=len(checks), failed=0, optimization_calls=0, directory=str(DEST))))
