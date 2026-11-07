"""No-solve entry validation: representation lift/projection and substitution.

Run in the foreground. This never calls optimize or presolve.
"""
import json
import sys
import time
from pathlib import Path

import strengthen as s
from strengthen_models import (run_cell, build, lift_start, backend,
                               assignment_solution, read, REAL_MODEL, SubstitutedModel)


def negative_checks():
    cell = next(c for c in s.make_plan('representation', [1])
                if c['case'] == 'n8_H5_4x1_dual' and c['arm'] == 'wafer')
    source = read(cell['source'])
    original = read(cell['values'])['values']
    x = build(backend.Config(**source['config']), 'wafer', original)
    try:
        values = lift_start(x, 'wafer', source, original)
        # Exchange same-Pjob, same-LP physical identities, preserving all
        # equipment operations: an unconstrained identity model accepts this,
        # but the explicit strict-FIFO formulation must reject it.
        labels = next(g.labels for g in x.groups if len(g.labels) > 1)
        a, b = labels[:2]
        for p in range(min(x.N, x.P)):
            for r in (0, 1):
                na = x.model.wafer_selectors[a, p, r].name
                nb = x.model.wafer_selectors[b, p, r].name
                values[na], values[nb] = values[nb], values[na]
        ta, tb = x.wafer_pickup[a].name, x.wafer_pickup[b].name
        values[ta], values[tb] = values[tb], values[ta]
        sol = x.model.createSol()
        for v in x.model.getVars(transformed=False):
            x.model.setSolVal(sol, v, values[v.name])
        rejected = not x.model.checkSol(sol, completely=True, original=True, printreason=False)
        x.model.freeSol(sol)
        assert rejected, 'Identity exchange incorrectly accepted under strict FIFO'
    finally:
        x.model.freeProb()
    # A symbolic test of interval pruning: a binding row remains; an
    # impossible fixed binary assignment is rejected, never silently skipped.
    m = SubstitutedModel(fixed_values={'fixed': 1})
    m.hideOutput()
    try:
        fixed = m.addVar(vtype='B', name='fixed')
        t = m.addVar(lb=0, ub=10, name='time')
        m.addCons(t <= 20)
        assert m.getNConss() == 0
        m.addCons(t >= 3 * fixed)
        assert m.getNConss() == 1
        try:
            m.addCons(fixed == 0)
        except ValueError:
            contradiction = True
        else:
            contradiction = False
        assert contradiction
    finally:
        m.freeProb()
    return dict(strict_fifo_identity_exchange_rejected=True,
                interval_pruning_binding_row_retained=True, contradictory_fixed_row_rejected=True)


def main():
    out = s.HERE / 'verification' / ('verified_' + str(time.time_ns()))
    out.mkdir(parents=True)
    cells = [c for c in s.make_plan('representation', [1]) if c['arm'] == 'wafer']
    cells += [c for c in s.make_plan('representation', [1])
              if c['arm'] == 'pjob' and c['case'] == 'n8_H5_mixed_dual']
    cells += [c for c in s.make_plan('rhythm_memory', [1, 2, 3]) if c['weight'] == 25]
    ref = s.QUALIFICATION / 'references/qualification_n8_mixed_dual'
    cells.append(dict(id='qualification_n8__wafer', case='qualification_n8', arm='wafer', seed=1,
                      source=str(ref / 'reference.json'), values=str(ref / 'common.json')))
    report = dict(solver_started=False, assets=s.inventory(), environment=s.environment(), cells=[],
                  negative_checks=negative_checks())
    for i, cell in enumerate(cells, 1):
        print(f'CHECK {i}/{len(cells)} {cell["id"]} (no optimization)', flush=True)
        dest = out / cell['id']
        dest.mkdir()
        record = run_cell(cell, dest, {}, check_only=True)
        record['cell'] = cell
        record['sources'] = {cell[k]: s.digest(Path(cell[k])) for k in ('source', 'values')}
        s.dump(dest / 'check.json', record)
        report['cells'].append(record)
        s.dump(out / 'entry_validation.json', report)
    assert s.inventory() == report['assets'], 'Source changed during verification'
    report['complete'] = True
    s.dump(out / 'entry_validation.json', report)
    s.dump(s.HERE / 'entry_validation.json', report)
    print(json.dumps(dict(complete=True, checks=len(cells), solver_started=False, report=str(out))), flush=True)


if __name__ == '__main__':
    main()
