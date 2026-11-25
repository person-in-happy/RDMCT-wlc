from shared_source import load_shared
load_shared(globals())
base_report=report


def report():
    base_report()
    certificates=[]
    for f in sorted((OUT/"runs").glob("t4_*/complete.json")):
        r=read(f)["report"]
        b=read(f.parent/"B/result.json")
        p=b.get("proof",{})
        kind=("new global Huber witness and lower bound" if r["arm"]=="free" else
              "identically zero within-recipe spread on the archived structure" if p.get("identically_zero_D")
              else "old lower bound minus 0.5 seconds" if p else "new fixed-structure solve")
        certificates.append(dict(n=r["n"],H=r["H"],seed=r["seed"],gap_percent=r["gap_percent"],arm=r["arm"],
              certificate=kind,lower=b["record"]["lower"],upper=b["record"]["upper"],relative_gap=b["record"]["gap"],
              original_lower=p.get("source_lower"),original_upper=p.get("source_upper"),source=p.get("source"),
              source_sha256=p.get("sha256"),new_certificate_sha256=sha(f.parent/"B/result.json")))
    if certificates:
        export_csv(OUT/"table4_certificates.csv",list(certificates[0]),certificates)


if __name__=="__main__":
    report()
