"""Read-only classification of old observations under the added release rule."""
from pathlib import Path
from collections import Counter, defaultdict
import gzip, hashlib, json, math, sys
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'JMS-version/model4_pjob_fifo_20261029'))
from pjob_order import order_report
from validate import validate


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


@lru_cache(None)
def words(counts):
    return math.factorial(sum(counts)) // math.prod(math.factorial(x) for x in counts)


def plan_lps(n, rank):
    rank //= 2**(n//2)
    remaining = [n//4]*4
    plan = []
    for _ in range(n):
        for i in range(4):
            if not remaining[i]:
                continue
            remaining[i] -= 1
            count = words(tuple(remaining))
            if rank < count:
                plan.append(i+1)
                break
            rank -= count
            remaining[i] += 1
    return plan


def main():
    report = dict(campaigns={}, construction={}, new_solver_runs=0)
    for tag, name in [('core', 'model4_core_all_20261028_fix1'),
                      ('ablation', 'model4_ablation_all_20261028_164314')]:
        folder = ROOT/'JMS-version/results'/name
        rows = []
        for run in sorted((folder/'runs').iterdir()):
            path = run/'result.json'
            if not path.exists():
                continue
            data = read(path)
            row = dict(id=run.name, result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       has_solution=bool(data.get('solutions')), status=data['status'])
            if row['has_solution']:
                row.update(cmax=data['cmax'], order=order_report(data))
                replay = validate(data)
                row['full_physical_valid'] = replay['valid']
                row['physical_errors'] = replay['errors']
                phase = run/'phase1.json'
                if phase.exists():
                    before = read(phase)
                    row['phase1_order'] = order_report(before) if before.get('solutions') else None
            rows.append(row)
            if len(rows) % 36 == 0:
                print(tag, 'reviewed', len(rows), flush=True)
        summary = dict(observations=len(rows), old_incumbents=sum(r['has_solution'] for r in rows),
                       strict_order_valid=sum(r.get('full_physical_valid', False) for r in rows))
        summary['valid_by_arm'] = dict(Counter(r['id'].split('__')[-1] for r in rows if r.get('full_physical_valid')))
        report['campaigns'][tag] = dict(summary=summary, rows=rows)
        print(tag, summary, flush=True)
    folder = ROOT/'JMS-version/gif/kexingyu/model4_pjob_20261027/evidence'
    for n in (8, 16, 32):
        path = folder/f'{n}wafer-index.jsonl.gz'
        kept = defaultdict(list)
        total = 0
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                plan = plan_lps(n, int(row['rank']))
                total += 1
                # Pjob3 contains LP3 followed by LP4. Other Pjobs have one LP.
                if max(i for i, lp in enumerate(plan) if lp == 3) < min(i for i, lp in enumerate(plan) if lp == 4):
                    kept[row['recipe']].append(row)
        lower = words((n//4, n//4, n//2)) * 2**(n//2)
        report['construction'][str(n)] = dict(reviewed=total, retained=sum(map(len, kept.values())),
            retained_by_recipe={recipe: len(rows) for recipe, rows in kept.items()},
            lower_bound_per_config=lower, index_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            examples={recipe: [rows[i] for i in sorted(set((0, len(rows)//2, len(rows)-1)))]
                      for recipe, rows in kept.items() if rows})
        print('construction', n, {k:v for k,v in report['construction'][str(n)].items() if k != 'examples'}, flush=True)
    (OUT/'strict_order_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')


if __name__ == '__main__':
    main()
