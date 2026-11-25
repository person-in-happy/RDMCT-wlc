"""Combine two validated eight-product schedules, minimizing their shift by physical replay."""
from dataclasses import asdict
from pathlib import Path
import sys
import time
from sweep import Config, HERE, HUB, MIX, OUT, atomic, cell, metrics, read, save, sha, validate
from seed import normalize_schedule
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from witness import sparse_witness


def join(cfg,d,delay,swap):
    doc=dict(config=asdict(cfg),schema=1,solutions=1,pairs=[],jobs=[],events=[],cycles=[])
    ncycles={2:0,3:0}
    ccount={2:0,3:0}
    for block in range(2):
        off=delay*block
        chamber={k:5-k if block and swap else k for k in (2,3)}
        labels={}
        for j in d["jobs"]:
            if j["product"]:
                port=int(j["origin"][2:])
                w=(port-1)%2+1+(2 if j["pjob"]=="Pjob2" else 0)
                labels[j["identity"]]=f"LP{(port-1)//2+2*block+1}_W{w}"
        jobnames={j["name"]:f'b{block}_{j["name"]}' for j in d["jobs"]}
        pairs={p["id"]:len(doc["pairs"])+i for i,p in enumerate(d["pairs"])}
        cycles={}
        for c in sorted(d["cycles"],key=lambda c:(c["chamber"],c["index"])):
            ch=chamber[c["chamber"]];q=ncycles[ch];ncycles[ch]+=1
            cycles[c["chamber"],c["index"]]=q
            assert c["mode"]!="clean"
            ccount[ch]+=1
            doc["cycles"].append(dict(c,chamber=ch,index=q,pairs=[pairs[p] for p in c["pairs"]],
                                    front=pairs[c["front"]],counter=ccount[ch],start=c["start"]+off,end=c["end"]+off))
        for p in d["pairs"]:
            doc["pairs"].append(dict(p,id=pairs[p["id"]],chamber=chamber[p["chamber"]],
                                     members=[labels.get(k,k) for k in p["members"]]))
        origins={}
        for j in d["jobs"]:
            item=dict(j,name=jobnames[j["name"]],pair=pairs[j["pair"]],identity=labels.get(j["identity"],j["identity"]))
            if item["product"]:
                item["origin"]=item["identity"].split("_")[0];origins[j["name"]]=item["origin"]
            for k in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):item[k]+=off
            doc["jobs"].append(item)
        for e in d["events"]:
            item=dict(e,start=e["start"]+off,end=e["end"]+off)
            if "pair" in e:item["pair"]=pairs[e["pair"]]
            if "job" in e:
                item["job"]=jobnames[e["job"]]
                if e["location"].startswith("LP"):item["location"]=origins[e["job"]]
            if e["location"].startswith("CH"):item["location"]=f"CH{chamber[int(e['location'][2:])]}"
            if "cycle" in e:
                ch=chamber[e["chamber"]];q=cycles[e["chamber"],e["cycle"]]
                item.update(chamber=ch,cycle=q,name=f"{e['name'].rsplit('_',2)[0]}_{ch}_{q}")
            doc["events"].append(item)
    doc["cmax"]=max(j["loan_end"] for j in doc["jobs"] if j["product"])
    return normalize_schedule(cfg,doc)


def main():
    dest=OUT/"two_blocks"
    dest.mkdir(exist_ok=True,parents=True)
    cfg=Config(**read(MIX/"input.json")["config"])
    src=HUB/"witnesses_grid_middle/D_n8_H10_mixed_dual/schedule.json";doc=read(src)
    sig={"source":sha(src),"input":sha(MIX/"input.json"),"implementation":sha(Path(__file__))}
    if (dest/"result.json").exists() and read(dest/"result.json")["signature"]==sig:return
    begin=time.monotonic()
    for swap in (False,True):
        checkpoint=dest/f"shift_{int(swap)}.json"
        if checkpoint.exists() and read(checkpoint)["signature"]==sig:continue
        good=None
        for shift in range(440,660):
            candidate=join(cfg,doc,shift,swap)
            if validate(candidate)["valid"]:
                good=shift;break
            if shift%25==0:
                dt=time.monotonic()-begin
                progress=dict(completed=int(swap),failed=0,shift=shift,elapsed=dt,eta_total=2*220*dt/max(1,(shift-439)+220*int(swap)))
                progress["eta_remaining"]=max(0,progress["eta_total"]-dt)
                atomic(dest/"progress.json",progress);print(progress,flush=True)
        assert good,swap
        step=next(i/8 for i in range(8*(good-1)+1,8*good+1) if validate(join(cfg,doc,i/8,swap))["valid"])
        atomic(checkpoint,dict(signature=sig,shift=step,swap=swap))
    pick=min((read(dest/f"shift_{int(s)}.json") for s in (False,True)),key=lambda r:r["shift"])
    out=join(cfg,doc,pick["shift"],pick["swap"])
    assert validate(out)["valid"]
    checked=cell.lift(cfg,sparse_witness(cfg,out),None,rebuild=True)
    assert checked
    d,a,_,replay,rows=checked
    save(dest/"schedule.json",d);save(dest/"assignment.json.gz",a)
    score=metrics(d);assert abs(score["secondary"]-3.4296875)<1e-8
    rec=dict(signature=sig,metrics=score,rows=rows,replay=replay,pick=pick,files={k:sha(dest/k) for k in ("schedule.json","assignment.json.gz")})
    atomic(dest/"result.json",rec);print(score,flush=True)
    atomic(dest/"progress.json",dict(completed=2,failed=0,elapsed=time.monotonic()-begin,eta_remaining=0))


if __name__=="__main__":
    main()
