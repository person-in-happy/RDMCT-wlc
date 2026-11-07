"""Isolated, matched reformulations; the historical solver stays unchanged.

No optimize call is made by check_only. Every accepted final assignment is
lifted back into a newly constructed, unchanged full FIFO model.
"""
from pathlib import Path
from collections import defaultdict
import gc
import math
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_fifo_20261029'
REVIEW = HERE.parent / 'reviewer_supplement_20261101'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REVIEW))
import model as backend
from scip_imports import scip
from pjob_order import encoding
from pjobs import groups_from_config
from revalidate import read
from run_experiments import dump, finite, incumbent_checks
from review_experiments import canonical_warm, physical_metrics
from validate import validate

REAL_MODEL = scip.Model


def same_replay(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_replay(a[k], b[k]) for k in a)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(same_replay(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=0, abs_tol=1e-5)
    return a == b


class SubstitutedModel(REAL_MODEL):
    """Exact substitution of fixed B/I variables, with interval tautology removal.

Bounds are the original variable bounds, never bounds inferred from the source
timings. All sync_ binaries remain decisions, as in the original refinement.
"""
    def __init__(self, *args, fixed_values, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_values = fixed_values
        self.substitutions = {}
        self.omitted_rows = 0

    def addVar(self, *args, **kwargs):
        name = kwargs.get('name', '')
        if kwargs.get('vtype', 'C') in ('B', 'I') and not name.startswith('sync_'):
            value = self.fixed_values[name]
            rounded = round(value)
            if abs(value - rounded) > 1e-5:
                raise ValueError('Nonintegral source variable: ' + name)
            lb = kwargs.get('lb', 0)
            ub = kwargs.get('ub', 1 if kwargs['vtype'] == 'B' else None)
            if (lb is not None and rounded < lb) or (ub is not None and rounded > ub):
                raise ValueError('Fixed variable outside original bounds: ' + name)
            self.substitutions[name] = rounded
            return rounded
        return super().addVar(*args, **kwargs)

    def addCons(self, cons, *args, **kwargs):
        if isinstance(cons, bool):
            if not cons:
                raise ValueError('Contradictory constant constraint after substitution')
            self.omitted_rows += 1
            return None
        low = high = 0.0
        for term, coefficient in cons.expr.terms.items():
            if len(term) == 0:
                low += coefficient
                high += coefficient
            elif len(term) == 1:
                var = term[0]
                a, b = var.getLbOriginal(), var.getUbOriginal()
                low += coefficient * (a if coefficient >= 0 else b)
                high += coefficient * (b if coefficient >= 0 else a)
            else:
                raise ValueError('Expected linear constraint')
        # ExprCons stores normalized lower/upper bounds in these fields.
        lhs, rhs = cons._lhs, cons._rhs
        if (lhs is None or low >= lhs) and (rhs is None or high <= rhs):
            self.omitted_rows += 1
            return None
        if (lhs is not None and high < lhs - 1e-7) or (rhs is not None and low > rhs + 1e-7):
            raise ValueError('Infeasible row after exact substitution')
        return super().addCons(cons, *args, **kwargs)


class WaferModel(REAL_MODEL):
    """Replace each inventory selector by a sum of physical-wafer selectors.

This is a controlled membership representation comparison. Pair-slot routes
and every equipment constraint are identical; it is not the historical model.
"""
    def __init__(self, *args, groups, product_bound, **kwargs):
        super().__init__(*args, **kwargs)
        self.selector_groups = groups
        self.product_bound = product_bound
        self.wafer_selectors = {}
        self.aggregate_selectors = {}
        self.selector_names = {
            f'pj_x_{g.identifier}_{p}_{r}': (g, p, r)
            for g in groups for p in range(product_bound) for r in (0, 1)}

    def addVar(self, *args, **kwargs):
        name = kwargs.get('name', '')
        if name not in self.selector_names:
            return super().addVar(*args, **kwargs)
        group, p, r = self.selector_names[name]
        selected = []
        for wafer in group.labels:
            y = super().addVar(vtype='B', name=f'wafer_y_{wafer}_{p}_{r}')
            self.wafer_selectors[wafer, p, r] = y
            selected.append(y)
        expression = scip.quicksum(selected)
        self.aggregate_selectors[name] = expression
        return expression


def build(cfg, arm, values):
    old = scip.Model
    try:
        if arm == 'substituted':
            scip.Model = lambda *a, **k: SubstitutedModel(*a, fixed_values=values, **k)
        elif arm == 'wafer':
            groups = groups_from_config(cfg)
            n = sum(g.count for g in groups)
            bound = min(n, cfg.max_pairs or n)
            scip.Model = lambda *a, **k: WaferModel(*a, groups=groups, product_bound=bound, **k)
        x = backend.Integrated(cfg)
    finally:
        scip.Model = old
    if arm == 'wafer':
        m = x.model
        codes = encoding(cfg)
        x.wafer_pickup = {w: m.addVar(lb=0, ub=x.H, name='wafer_pickup_' + w) for w in codes}
        tasks = defaultdict(list)
        for w, code in codes.items():
            tasks[code['pjob']].append(w)
            m.addCons(scip.quicksum(y for (label, _, _), y in m.wafer_selectors.items() if label == w) == 1)
            for p in range(min(x.N, x.P)):
                for r in (0, 1):
                    y = m.wafer_selectors[w, p, r]
                    start = x.jobs[f'prod_{p}_{r}']['first']['s']
                    x.eq(x.wafer_pickup[w], start, y)
        for labels in tasks.values():
            labels.sort(key=lambda w: codes[w]['pjob_index'])
            for left, right in zip(labels, labels[1:]):
                m.addCons(x.wafer_pickup[right] >= x.wafer_pickup[left] + cfg.atr_handling)
        x.original_dimensions = dimensions(x)
    return x


def dimensions(x):
    m = x.model
    return dict(variables=m.getNVars(), constraints=m.getNConss(),
        linear_nonzeros=sum(len(m.getValsLinear(c)) for c in m.getConss()),
        types={t: sum(v.vtype() == t for v in m.getVars()) for t in ('BINARY', 'INTEGER', 'CONTINUOUS')})


def lift_start(x, arm, source, values):
    result = dict(values)
    if arm == 'wafer':
        by_slot = {(pair['id'], r): w for pair in source['pairs'] for r, w in enumerate(pair['members'])}
        jobs = {job['identity']: job for job in source['jobs'] if job['product']}
        for (w, p, r), var in x.model.wafer_selectors.items():
            result[var.name] = int(by_slot.get((p, r)) == w)
        for w, var in x.wafer_pickup.items():
            result[var.name] = jobs[w]['loan_start']
    return canonical_warm(x, result)


def assignment_solution(x, values):
    sol = x.model.createSol()
    for v in x.model.getVars(transformed=False):
        x.model.setSolVal(sol, v, values[v.name])
    if not x.model.checkSol(sol, completely=True, original=True, printreason=True):
        x.model.freeSol(sol)
        raise RuntimeError('Assignment violates original constraints')
    return sol


def assert_wafer_decode(x, sol, data):
    if not isinstance(x.model, WaferModel):
        return
    expected = {(p['id'], r): w for p in data['pairs'] for r, w in enumerate(p['members'])}
    for (w, p, r), y in x.model.wafer_selectors.items():
        if x.model.getSolVal(sol, y) > .5 and expected.get((p, r)) != w:
            raise RuntimeError('Wafer selectors disagree with decoded physical identities')


def audit_full(cfg, values, reference):
    """Rebuild the unmodified full MILP, with no optimize/presolve call."""
    start = time.monotonic()
    x = backend.Integrated(cfg)
    try:
        sol = assignment_solution(x, values)
        replay = x.result(solution=sol)
        check = validate(replay)
        if not check['valid']:
            raise RuntimeError('Lifted original solution failed physical replay')
        for field, key in (('events', 'name'), ('jobs', 'name'), ('pairs', 'id')):
            a = {row[key]: row for row in reference[field]}
            b = {row[key]: row for row in replay[field]}
            if not same_replay(a, b):
                raise RuntimeError('Full-model replay changed ' + field)
        if not same_replay(reference['cycles'], replay['cycles']):
            raise RuntimeError('Full-model replay changed chamber cycles')
        x.model.freeSol(sol)
        return dict(valid=True, original_model_check=True, physical_validation=check,
                    seconds=time.monotonic() - start, solver_started=False,
                    dimensions=x.original_dimensions)
    finally:
        x.model.freeProb()


def run_cell(cell, dest, settings, check_only=False):
    import psutil
    dump(dest / 'phase.json', dict(phase='construction'))
    source = read(cell['source'])
    original = read(cell['values'])['values']
    cfg = backend.Config(**source['config'])
    source_metrics = physical_metrics(source)
    begin = time.monotonic()
    x = build(cfg, cell['arm'], original)
    m = x.model
    result_values = None
    try:
        warm_values = lift_start(x, cell['arm'], source, original)
        refinement = cell['arm'] == 'substituted'
        upper = source_metrics['product_cmax']
        if refinement:
            m.addCons(x.cmax <= upper + 1e-6)
            m.setObjective(sum(x.waits) + 10 * x.max_wait + cell['weight'] * sum(x.rhythm), 'minimize')
        else:
            m.setObjective(x.cmax, 'minimize')
        warm = assignment_solution(x, warm_values)
        replay = x.result(solution=warm)
        assert_wafer_decode(x, warm, replay)
        if not validate(replay)['valid']:
            raise RuntimeError('Warm physical replay failed')
        dim = dimensions(x)
        selector_count = len(m.wafer_selectors) if cell['arm'] == 'wafer' else 0 if refinement else len(x.pair.member)
        construction = dict(dimensions=dim, build_seconds=time.monotonic() - begin,
            source_metrics=source_metrics, selector_variables=selector_count,
            N=x.N, G=len(x.groups), candidate_pairs=x.P, candidate_cycles=x.Q,
            full_candidate_space=not x.bounded and not refinement,
            candidate_bound_restricted=x.bounded,
            build_rss_mb=psutil.Process().memory_info().rss / 1024**2,
            substituted_variables=len(getattr(m, 'substitutions', {})),
            removed_tautologies=getattr(m, 'omitted_rows', 0))
        dump(dest / 'build.json', construction)
        if check_only:
            sol = warm
            data = replay
            record = dict(state='checked', solve_seconds=0, solver_started=False)
        else:
            m.setIntParam('parallel/maxnthreads', 1)
            m.setIntParam('randomization/randomseedshift', cell['seed'])
            m.setIntParam('separating/maxroundsroot', 1)
            m.setIntParam('separating/maxrounds', 0)
            m.setRealParam('limits/memory', settings['memory_mb'])
            m.setRealParam('limits/time', settings['stage2_limit'] if refinement else settings['time_limit'])
            m.setLogfile(str(dest / 'solver.log'))
            m.addSol(warm)
            dump(dest / 'phase.json', dict(phase='solve'))
            m.optimize()
            data = x.result()
            checks = incumbent_checks(m)
            if not checks['original_model_check']:
                raise RuntimeError('Reformulated model check failed')
            data.update(checks)
            sol = m.getBestSol()
            assert_wafer_decode(x, sol, data)
            record = dict(state=str(m.getStatus()), solve_seconds=m.getSolvingTime(),
                optimized_objective=m.getObjVal(), dual_bound=m.getDualbound(), gap=m.getGap(),
                nodes=m.getNNodes(), lp_iterations=m.getNLPIterations(), solver_started=True,
                solve_end_rss_mb=psutil.Process().memory_info().rss / 1024**2)
        derived = physical_metrics(data)
        if not validate(data)['valid'] or (refinement and derived['product_cmax'] > upper + 2e-4):
            raise RuntimeError('Physical validation or Cmax cap failed')
        result_values = dict(original) if refinement else {}
        result_values.update({v.name: m.getSolVal(sol, v) for v in m.getVars(transformed=False)})
        if cell['arm'] == 'wafer':
            for name, expression in m.aggregate_selectors.items():
                result_values[name] = m.getSolVal(sol, expression)
        if refinement:
            # All omitted auxiliary B/I values must remain those of the input.
            for name, value in m.substitutions.items():
                if abs(result_values[name] - value) > 1e-6:
                    raise RuntimeError('Fixed discrete value changed: ' + name)
        if check_only:
            m.freeSol(sol)
        data.update(experiment_scope=cell['arm'], refinement_weight=cell.get('weight'),
                    representation_comparison='membership_only_same_pair_slot_routes',
                    full_candidate_space=not x.bounded and not refinement)
        if cell['arm'] == 'wafer':
            data.update(pjob_inventory_variables=0, wafer_membership_variables=selector_count)
    finally:
        m.freeProb()
    del x, m
    gc.collect()
    dump(dest / 'phase.json', dict(phase='full_model_audit'))
    audit = audit_full(cfg, result_values, data)
    dump(dest / 'full_model_audit.json', audit)
    record.update(complete=True, valid=True, source_metrics=source_metrics, metrics=derived,
                  original_model_check=True, full_model_audit=audit,
                  **{k: v for k, v in construction.items() if k != 'source_metrics'})
    if not check_only:
        dump(dest / 'result.json', finite(data))
        dump(dest / 'variables.json', dict(values=result_values))
    dump(dest / 'phase.json', dict(phase='complete'))
    return finite(record)
