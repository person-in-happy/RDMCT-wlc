"""Independently check the confirmed mean, within-recipe spread and actual-clean objective."""
import argparse
import csv
import importlib.util

from supplement import HERE, OUT, checked, load

spec=importlib.util.spec_from_file_location("manuscript_audit",HERE.parent/"quota_objective_20261125/verify_manuscript.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
audit.OUT=OUT.parent
audit.MANUSCRIPT=audit.JMS/"JMS_Review_CN.tex"


def publish_supplement():
    manifest=load(OUT/"manifest.json")
    groups={"threshold":[],"structure":[],"range":[]}
    for name,job in manifest.items():
        src=OUT/job["key"]
        if not checked(src,job):
            raise ValueError(name)
        result=load(src/"result.json")
        values=result["measured"]
        row=dict(name=name,seed=result["seed"],f_A=values["cmax"],f_B=values["secondary"],
                 mean=values["mean_residence"],spread=values["residence_range"],clean_deficit=values["clean_deficit"],
                 status=result["record"]["status"],source=job["key"])
        if name.startswith("grid_"):
            case,ga,gb=name[5:].split("__")
            groups["threshold"].append(dict(case=case,gA=ga,gB=gb,**row))
        elif name.startswith("structure_"):
            groups["structure"].append(row)
        else:
            independent=audit.independent(audit.read(src/"schedule.json"),True)
            weight=job["settings"]["range_weight"]
            expected=independent["mean_residence"]+weight*independent["residence_range"]+independent["clean_deficit"]
            assert abs(expected-float(row["f_B"]))<2e-4
            groups["range"].append(dict(range_weight=weight,**row))
    for name,rows in groups.items():
        with (OUT/f"{name}_cells.csv").open("w",encoding="utf-8",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial",action="store_true")
    args=parser.parse_args()
    publish_supplement()
    audit.main(args.partial,True)
