"""Select the shortest verified global-B-optimal witness separately from recorded stop points."""
from collections import defaultdict
from pathlib import Path

from jobs import CELLS, EPS, HERE, JMS, ONE, OUT, SEEDS, case, folder, read, sha, write
from report import export_csv
from score import metrics


def verified_schedule(directory):
    path=directory/"schedule.json"
    assignment=directory/"assignment.json.gz"
    if not path.is_file() or not assignment.is_file():
        return None
    for name in ("primary.json","result.json"):
        proof=directory/name
        if not proof.is_file():
            continue
        d=read(proof)
        files=d.get("files",dict())
        if (d.get("schedule_sha256",files.get("schedule.json"))!=sha(path)
                or d.get("assignment_sha256",files.get("assignment.json.gz"))!=sha(assignment)
                or not d.get("replay",{}).get("valid")
                or d.get("rows",d.get("replayed_rows",d.get("original_rows",0)))<=0):
            continue
        schedule=read(path)
        return dict(source=str(path.relative_to(JMS)),qualified_by=str(proof.relative_to(JMS)),
                    schedule_sha256=sha(path),assignment_sha256=sha(assignment),record_sha256=sha(proof),
                    config=schedule["config"],**metrics(schedule))
    return None


def publish():
    source=ONE/"runs/D_n8_H3_mixed_dual__s3/A/witness_1795511516834780600/schedule.json"
    primary_root=OUT.parent/"residence_objective_20261125"
    primary_code=HERE.parent/"residence_objective_20261125"
    cp=primary_root/"primary_relaxation_tight/result.json"
    bound=read(cp)
    assert (bound["cap"],bound["status"],bound["lower"])==(552,"INFEASIBLE",553)
    assert bound["source_sha256"]==sha(source) and bound["driver_sha256"]==sha(primary_code/"tight_primary.py")
    assert bound["base_sha256"]==sha(primary_code/"primary_relaxation.py")
    cpscope=read(source)["config"]
    registry=[p.parent for p in (OUT/"best_reuse").rglob("schedule.json")]
    registry += [p.parent for source in OUT.glob("witnesses*") if source.is_dir() for p in source.rglob("schedule.json")]
    registry += [p.parent for p in (OUT/"shortest_fixed_order").rglob("schedule.json")]
    registry += [p.parent for p in (OUT/"parallel_block_reuse").rglob("schedule.json")]
    registry += [p.parent for p in (OUT/"reuse/transfers").rglob("schedule.json")]
    registry += [p.parent for p in (OUT/"runs").glob("t4*/*/schedule.json")]
    pool=OUT/"reuse/warm_pool.json"
    if pool.exists():
        registry += [Path(p) for candidates in read(pool).values() for p in candidates]
    # The external archive was already validated and linked to its supplying raw file.
    archive=primary_root/"reuse/complete_candidates.json"
    if archive.exists():
        registry += [(JMS.parent/d["source"]).parent for d in read(archive)
                     if d.get("source","").endswith("/schedule.json") and not d.get("location")]
    configs={(n,h):read(ONE/"inputs"/case(n,h)/"input.json")["config"] for n,h in CELLS}
    candidates=defaultdict(list)
    for loc in sorted(set(registry)):
        verified=verified_schedule(loc)
        if verified:
            cfg=verified.pop("config")
            for key in CELLS:
                if cfg==configs[key]:
                    candidates[key].append(verified)
    selected=[]
    primary=[]
    for (n,h), witnesses in candidates.items():
        control=folder(f"t4_1_{n}_{h}_1_free")/"B/result.json"
        certificate=read(control)
        assert certificate["eligible"] and certificate["record"]["gap"]<=1e-7
        optimal=certificate["record"]["lower"]
        competitive=[w for w in witnesses if abs(w["secondary"]-optimal)<=1.e-6]
        pick=min(competitive,key=lambda x:(round(x["cmax"],5),x["source"]))
        selected.append(dict(n=n,H=h,**pick,B_lower=optimal,free_proof=str(control.relative_to(JMS)),
                             free_proof_sha256=sha(control),number_of_verified_files=len(witnesses),
                             same_B_witnesses=len({w["schedule_sha256"] for w in competitive})))
        if n!=8:
            continue
        assert all(v==cpscope[k] for k,v in configs[n,h].items() if k!="cleaning_interval")
        for seed in SEEDS:
            gate=folder(f"primary_{n}_{h}_{seed}")/"primary.json"
            d=read(gate)
            assert abs(d["record"]["upper"]-bound["lower"])<EPS
            primary.append(dict(n=n,H=h,seed=seed,cmax=d["record"]["upper"],gate_lower=d["record"]["lower"],
                                physical_global_lower=bound["lower"],physical_global_gap=0,
                                gate_source=str(gate.relative_to(JMS)),gate_sha256=sha(gate),
                                proof_source=str(cp.relative_to(JMS)),proof_sha256=sha(cp)))
    selected.sort(key=lambda r:(r["n"],r["H"]))
    primary.sort(key=lambda r:(r["H"],r["seed"]))
    assert len(selected)==len(CELLS) and len(primary)==6
    export_csv(OUT/"free_B_shortest_verified.csv",list(selected[0]),selected)
    export_csv(OUT/"primary_A_certificates.csv",list(primary[0]),primary)
    write(OUT/"reuse/additional_certificates.json",dict(free_witnesses=selected,primary_certificates=primary,
          selection="smallest product-return time among verified schedules whose new secondary equals its global lower bound",
          original_stopping_data="all seed-specific actual A, B and AB endpoints retain their original source and gap"))


if __name__=="__main__":
    publish()
