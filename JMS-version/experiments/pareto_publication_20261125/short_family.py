"""Check the continuous native witness for the short-makespan arc through the left limit at 812."""
import itertools
import sys
from pathlib import Path
from archive import HERE, JMS, OUT, RESULTS, read, sha

sys.path.insert(0, str(HERE.parent/"pareto_square_20261125"))
from fixed import sweep


def active_metrics(doc):
    products = {r["identity"]:r for r in doc["jobs"] if r["product"]}
    recipes = {r["id"]:r["mode"] for r in doc["pairs"]}
    res = {w:r["unload_start"]-r["load_end"]-
           (doc["config"]["full_time"] if recipes[r["pair"]]=="4x1" else 2*doc["config"]["mix_time"])
           for w,r in products.items()}
    scores = sweep.metrics(doc)
    diff = {(a,b) for a,b in itertools.permutations(products,2)
            if recipes[products[a]["pair"]] == recipes[products[b]["pair"]]
            and abs(res[a]-res[b]-scores["residence_range"]) < 1e-6}
    last = {w for w,r in products.items() if abs(r["loan_end"]-scores["cmax"]) < 1e-6}
    return diff, last


def main():
    sources = [RESULTS/"pareto_scales_20261125/continuous16/endpoint810",
               RESULTS/"pareto_square_20261125/fixed/short16/cap_812"]
    model = sweep.Integrated(sweep.Config(**read(sources[0]/"schedule.json")["config"]))
    m = model.model
    kinds = {r.getConshdlrName() for r in m.getConss(transformed=False)}
    assert kinds == {"linear"}, kinds
    integers = {v.name for v in m.getVars(transformed=False) if v.vtype()!="CONTINUOUS"}
    vals = []
    binding = []
    for src in sources:
        z = sweep.cell.values(src/"assignment.json.gz")
        z = {k:round(num) if abs(num-round(num))<=1e-6 else num for k,num in z.items()}
        vals.append(z)
        sol = sweep.cell.solution(model,z)
        assert m.checkSol(sol, original=True, completely=True)
        doc = model.result(solution=sol)
        binding.append(active_metrics(doc))
        m.freeSol(sol)
    left, right = vals
    assert all(left.get(k,0)==right.get(k,0) for k in integers)
    common_spread = binding[0][0] & binding[1][0]
    common_last = binding[0][1] & binding[1][1]
    assert common_spread and common_last
    knots = []
    for a in (0, .125, .375, .50, .65, .875, 1):
        z = {k:(1-a)*left.get(k,0)+a*right.get(k,0) for k in left.keys() | right.keys()}
        sol = sweep.cell.solution(model,z)
        assert m.checkSol(sol, original=True, completely=True)
        doc = model.result(solution=sol)
        m.freeSol(sol)
        replay = sweep.validate(doc)
        r = sweep.metrics(doc)
        c = 810+2*a
        assert replay["valid"] and abs(r["cmax"]-c)<1e-6 and r["clean_deficit"]==0
        assert abs(r["mean_residence"]-(7.625-.125*(c-810)))<1e-6
        assert abs(r["residence_range"]-(30-(c-810)))<1e-6
        knots.append(dict(cap=c,score=r["secondary"],physical_checks=replay["checks"]))
    sweep.atomic(OUT/"short16_family.json", dict(
        reachable_interval=[810,812], certified_interval=[810,811], upper_open_at_jump=812,
        source_sha256={(s/n).relative_to(JMS).as_posix():sha(s/n) for s in sources for n in ("schedule.json","assignment.json.gz")},
        original_rows=m.getNConss(), unchanged_integer_decisions=len(integers), original_constraint_types=sorted(kinds),
        common_spread_pair=sorted(common_spread), common_last_wafer=sorted(common_last),
        knots=knots, implementation_sha256=sha(Path(__file__))))
    m.freeProb()
    print(knots)


if __name__ == "__main__":
    main()
