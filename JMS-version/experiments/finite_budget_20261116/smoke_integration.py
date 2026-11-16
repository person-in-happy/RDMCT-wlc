"""Small CPU-only integration checks; outputs are NOT publication experiments."""
import argparse
import subprocess
import sys
import finite_budget as f


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    a = p.parse_args()
    out = f.Path(a.output).resolve()
    if out.exists() or not out.is_relative_to(f.JMS / "results"):
        raise ValueError("Use a fresh isolated test directory")
    c = f.source_records()[0]
    d = f.read(c["source"])
    metrics = f.physical_metrics(d)
    c.update(config=d["config"], input_metrics=metrics,
             scales={"cmax":metrics["cmax"],"secondary":max(1,metrics["secondary"])})
    cells = [dict(case=c["case"],backend="D",suite="preparation" if arm=="spbs" else "objectives",
                  seed=1,training_seed=1,method="scip",arm=arm,budget=2.,id="smoke_"+arm)
             for arm in ("primary","two_stage","joint_0.1","spbs")]
    out.mkdir(parents=True)
    f.dump(out / "campaign.json", dict(schema=1,cases=[c],cells=cells,assets=f.inventory(),
            sources={c[k]:f.sha(c[k]) for k in ("source","values")},
            purpose="Software integration test only; 2-second limits; exclude from manuscript"))
    f.dump(out / "contract.json", dict(campaign_sha256=f.sha(out / "campaign.json")))
    for cell in cells:
        r = subprocess.run([sys.executable,"-X","utf8","-u",str(f.Path(f.__file__)),"worker",
                            "--campaign",str(out),"--cell",cell["id"]])
        if r.returncode:
            raise RuntimeError("Integration check failed: "+cell["id"])
        e = f.read(out / "runs" / cell["id"] / "evidence.json")
        assert e["valid"]
        assert e["metrics"]["cmax"] <= metrics["cmax"] + 2e-4 or cell["arm"].startswith("joint_")
    f.dump(out / "checks.json", dict(passed=4,formal_experiment=False))


if __name__ == "__main__":
    main()
