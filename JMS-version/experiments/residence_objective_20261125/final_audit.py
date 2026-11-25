"""Verify every manuscript endpoint and the exact cutoffs of shared comparator traces."""
import csv
import json
from pathlib import Path

from jobs import EPS, HERE, OUT, folder, read, sha, tasks, write
from report import check, report


def rows(name):
    with (OUT/name).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def run():
    assert len(tasks())==75
    for key in tasks():
        complete=folder(key)/"complete.json"
        check(key,sha(complete))
    report()
    four=rows("table4_seeds.csv")
    five=rows("table5_seeds.csv")
    assert len(four)==len({(r["level"],r["n"],r["H"],r["arm"],r["seed"]) for r in four})==81
    assert len(five)==len({(r["arm"],r["seed"]) for r in five})==15
    assert all(int(r["completed"])==3 for r in rows("table4_means.csv")+rows("table5_means.csv"))
    shared=[]
    for r in five:
        if r["arm"]=="full":
            continue
        key=f"t5_{r['seed']}_{r['arm']}"
        d=folder(key)
        file=d/"A_reuse.json"
        if not file.exists():
            continue
        h=read(file)
        if "trace_sha256" not in h:
            continue
        src=Path(h["source"])
        stream=src/"A_cut_times.jsonl"
        vectors=src/"A_objectives.jsonl"
        assert sha(stream)==h["cut_times_sha256"] and sha(vectors)==h["trace_sha256"]
        assert sha(src/"result.json")==h["source_sha256"]
        cuts=[json.loads(line) for line in stream.read_text().splitlines()]
        assert all(k==i for i,(_,k) in enumerate(cuts,1)) and all(a[0]<=b[0] for a,b in zip(cuts,cuts[1:]))
        at=h["restored_s"]
        count=sum(t<=at for t,_ in cuts)
        assert count==h["restored_calls"]
        if abs(float(r["observed_s"])-at)<1e-5:
            assert count==int(r["calls"])
            scores=[json.loads(line) for line in vectors.read_text().splitlines()]
            before=[s for s in scores if s["at"]<=at]
            ref=read(folder("ref5_"+r["seed"])/"timing.json")
            hits=[s for s in before if s["a"]<=ref["f_A"]+EPS and s["other_b"]<=ref["f_B"]+EPS]
            if hits:
                winner=min(hits,key=lambda s:s["at"])
            else:
                lowest=min(s["a"] for s in before)
                winner=min((s for s in before if s["a"]<=lowest+EPS),key=lambda s:s["other_b"])
            assert abs(winner["a"]-float(r["f_A"]))<EPS and abs(winner["other_b"]-float(r["f_B"]))<EPS
        shared.append(dict(seed=int(r["seed"]),method=r["arm"],cutoff_s=at,calls=count,
                           previous_cut_s=next((t for t,_ in reversed(cuts) if t<=at),None),
                           following_cut_s=next((t for t,_ in cuts if t>at),None),
                           original_traced_calls=len(cuts),primary_reuse_sha256=sha(file)))
    data=dict(objective=HERE.name,total_jobs=75,table4_seed_rows=len(four),table5_seed_rows=len(five),
              complete_seed_groups=True,shared_cutoff_replays=shared,
              tables={name:sha(OUT/name) for name in ("table4_means.csv","table4_seeds.csv","table5_means.csv",
                      "table5_seeds.csv","table5_provenance.csv","free_B_shortest_verified.csv","primary_A_certificates.csv")})
    write(OUT/"final_audit.json",data)
    print(json.dumps(data,ensure_ascii=False))


if __name__=="__main__":
    run()
