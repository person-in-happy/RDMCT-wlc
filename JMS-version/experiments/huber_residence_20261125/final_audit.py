from collections import Counter
import csv
from jobs import EPS, JMS, OUT, folder, read, sha, tasks, write
from report import check,report


def rows(name):
    with (OUT/name).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def run():
    kinds=Counter()
    methods=[]
    for key in tasks():
        d=folder(key)
        r=check(key,sha(d/"complete.json"))
        if key.startswith("t4_"):
            record=read(d/"B/result.json")
            if key.endswith("_free"):
                assert record["record"]["gap"]<=1e-6
                kinds["global_free_B_witness"]+=1
            elif "proof" in record:
                p=record["proof"]
                original=JMS/p["source"]/"result.json"
                assert sha(original)==p["sha256"]
                lb=read(original)["record"]["lower"]
                assert abs(max(0.,lb-p["maximum_objective_reduction"])-record["record"]["lower"])<EPS
                kinds["constant_D_fixed_structure" if p["identically_zero_D"] else "transported_fixed_lower_bound"]+=1
            else:
                kinds["new_fixed_solve"]+=1
        if key.startswith("t5_"):
            file=d/"A_reuse.json"
            if file.exists():
                proof=read(file)
                src=JMS/proof["source"]/"result.json"
                assert sha(src)==proof["source_sha256"]
                old=read(src)
                assert r["observed_s"]==old["observed_s"] and r["calls"]==old["calls"]
                assert abs(r["f_A"]-old["f_A"])<EPS
                audit=dict(method=key,classification=proof["reason"],source=str(src.relative_to(JMS)),
                           source_sha256=sha(src),evidence=sha(file))
            else:
                audit=dict(method=key,classification="new matched native primary and, where reached, secondary search",
                           source=str((d/"progress.json").relative_to(JMS)),evidence=sha(d/"progress.json"))
            methods.append(audit)
    report()
    four=rows("table4_seeds.csv")
    five=rows("table5_seeds.csv")
    assert len(four)==len({(r["level"],r["n"],r["H"],r["arm"],r["seed"]) for r in four})==81
    assert len(five)==len({(r["arm"],r["seed"]) for r in five})==15
    assert all(int(r["completed"])==3 for r in rows("table4_means.csv")+rows("table5_means.csv"))
    assert all(abs(float(x["secondary"])-float(x["mean_residence"])-float(x["huber_penalty"])-float(x["clean_deficit"]))<EPS for x in four)
    result=dict(jobs_verified=75,table4_seed_rows=81,table5_seed_rows=15,fixed_and_free=dict(kinds),
                comparator_traces=methods,old_full_references_reused=3,
                tables={n:sha(OUT/n) for n in ("table4_seeds.csv","table4_means.csv","table5_seeds.csv",
                      "table5_means.csv","table5_provenance.csv","table4_certificates.csv","free_B_shortest_verified.csv")})
    write(OUT/"final_audit.json",result)
    return result


if __name__=="__main__":
    run()
