"""Replay search proposals and check every retained integer witness directly against the shared native model."""
from pathlib import Path
import sys
from support import HERE,JMS,OUT,read,write,digest
sys.path.insert(0,str(HERE.parent/"square_residence_20261125"))
from solver import cell
from score import metrics
sys.path.insert(0,str(HERE.parent/"table3_mixed16_20261125"))
from replay_moves import attach_hands,reconstruct,validate
from prepare import sparse_witness,configuration
from model import Integrated


def checked_candidates():
    candidates={}
    rejected=[]
    for path in sorted((OUT/"search").glob("*/p_*.json")):
        try:
            d=reconstruct(read(path))
            fitted=attach_hands(d)
            valid=validate(d)
            if not fitted or not valid["valid"]:
                rejected.append({"path":str(path.relative_to(JMS)),"errors":valid["errors"][:3]})
                continue
            m=metrics(d)
            key=m["cmax"],m["secondary"]
            candidates.setdefault(key,(path,d,m))
        except (KeyError,StopIteration,ValueError,AssertionError) as e:
            rejected.append({"path":str(path.relative_to(JMS)),"reason":repr(e)})
    best=float("inf");selected=[]
    for (c,f),value in sorted(candidates.items()):
        if f<best:selected.append(value);best=f
    return selected,rejected,len(candidates)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    selected,rejected,n=checked_candidates()
    cfg=configuration()
    todo=[(f,d,m) for f,d,m in selected if not (OUT/"native"/f.parent.name/f.stem/"result.json").exists()]
    print(f"{len(todo)} new original-model witnesses, historical 10–30 s initialization plus 2–4 s per retained schedule",flush=True)
    if todo:
        x=Integrated(cfg);model=x.model
        original=model.getNConss();model.setRealParam("numerics/feastol",1e-8)
        vars={v.name:v for v in model.getVars(transformed=False)}
        for idx,(f,d,m) in enumerate(todo):
            dest=OUT/"native"/f.parent.name/f.stem;dest.mkdir(parents=True,exist_ok=True)
            vals=sparse_witness(cfg,d);s=cell.solution(x,vals)
            val=lambda v:model.getSolVal(s,v)
            model.setSolVal(s,x.max_wait,max(val(v) for v in x.waits))
            for c in cfg.chambers:
                for q in range(2,x.Q):
                    active=val(x.keep[c,q])>.5 and val(x.keep[c,q-1])>.5
                    z=abs(val(x.cy.start[c,q])-2*val(x.cy.start[c,q-1])+val(x.cy.start[c,q-2]))
                    model.setSolVal(s,vars[f"rhythm_{c}_{q}"],max(0,z-(0 if active else x.M)))
            assert model.checkSol(s,original=True,completely=True)
            decoded=x.result(solution=s);zz=metrics(decoded);replay=validate(decoded)
            assert replay["valid"] and abs(zz["secondary"]-m["secondary"])<1e-7 and abs(zz["cmax"]-m["cmax"])<1e-7
            assignment=cell.sparse({k:val(v) for k,v in vars.items()});model.freeSol(s)
            cell.save(dest/"schedule.json",decoded);cell.save(dest/"assignment.json.gz",assignment)
            write(dest/"result.json",dict(original_rows=original,metrics=zz,replay=replay,source=str(f.relative_to(JMS)),source_sha256=digest(f),
                        files={p:digest(dest/p) for p in ("schedule.json","assignment.json.gz")}))
            print(f"{idx+1}/{len(todo)}, C={zz['cmax']:.2f}, B={zz['secondary']:.6g}",flush=True)
        model.freeProb()
    write(OUT/"search_replay.json",dict(unique_valid_coordinates=n,rejected=rejected,selected=[str(f.relative_to(JMS)) for f,d,m in selected]))


if __name__=="__main__":main()
