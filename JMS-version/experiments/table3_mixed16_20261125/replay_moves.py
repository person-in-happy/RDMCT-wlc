"""Recover every product, dummy, chamber rotation and loan directly from timed outer-model actions."""
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
import sys
from prepare import OUT,JMS,configuration,validate,normalize_schedule,sha,read
from candidate import atomic
from grippers import attach_hands


def reconstruct(v):
    cfg=configuration()
    keys=sorted(int(k[5:]) for k in v if k.startswith("kind_"))
    kind={k:v[f"kind_{k}"] for k in keys if v[f"kind_{k}"]}
    members=defaultdict(list);names={}
    for typ,task in enumerate(cfg.pjobs,1):
        order=sorted((i for i in range(16) if kind[keys[v[f"batch_{i}"]]]==typ),
                     key=lambda i:(v[f"port_{i}"],v[f"origin_pick_{i}"],v[f"al_{i}"]))
        for w,i in zip(task["wafers"],order,strict=True):
            assert int(w.split("_")[0][2:])==v[f"port_{i}"]+1
            names[i]=w
            g=keys[v[f"batch_{i}"]]
            members[g,v[f"front_{i}"] if typ==1 else "prod"].append(i)
    pairids={};pairs=[];series=[];steps={};loans=[];cy=[];events=[]
    def event(name,kind,loc,robot,t,duration,**extra):
        events.append(dict(name=name,kind=kind,location=loc,robot=robot,start=t,end=t+duration,**extra))
    modes={1:"4x1",2:"2x2"}
    def pair(key,load,unload):
        if key in pairids:return pairids[key]
        g,side=key;p=len(pairs);pairids[key]=p
        chamber=2+g//10;loc=f"CH{chamber}"
        event(f"load_{p}","pair_load",loc,"VTR",load,1,pair=p)
        event(f"unload_{p}","pair_unload",loc,"VTR",unload,1,pair=p)
        ids=members[key];labels=[names[i] for i in ids]
        pairs.append(dict(id=p,members=labels,chamber=chamber,mode=modes[kind[g]]))
        steps[p]=load,unload
        for r in range(2):
            n=f"w_{p}_{r}";prod=r<len(ids)
            if prod:
                i=ids[r];w=names[i];home=w.split("_")[0]
                fields=(("origin_pick","origin_pick",home,4),("al_put","al","AL",4),("al_pick","ap","AL",4),
                        ("upper_put","up","U",4),("source_pick","sp","U",1),("destination_put","dp","L",1),
                        ("lower_pick","lp","L",4),("origin_put","origin_put",home,4))
                for action,k,site,dt in fields:
                    event(f"{n}_{action}",action,site,"VTR" if k in ("sp","dp") else "ATR",v[f"{k}_{i}"],dt,job=n)
                t0,t1=v[f"origin_pick_{i}"],v[f"origin_put_{i}"]+4
            else:
                j=r-len(ids)
                w=None;home="VS"
                t0,t1=v[f"vs_in_{key}_{j}"],v[f"vs_out_{key}_{j}"]+1
                event(f"{n}_source_pick","source_pick","VS","VTR",t0,1,job=n)
                event(f"{n}_destination_put","destination_put","VS","VTR",t1-1,1,job=n)
                labels.append(None);loans.append((t0,t1,p,r,len(series)))
            series.append(dict(name=n,pair=p,identity=w,product=prod,origin=home,loan_start=t0,loan_end=t1,
                               load_start=load,load_end=load+1,unload_start=unload,unload_end=unload+1))
        return p
    for c in (2,3):
        parts=[]
        for g,ty in kind.items():
            if g//10!=c-2:continue
            if ty==1:
                back=pair((g,0),v[f"bl_{g}"],v[f"bu_{g}"])
                front=pair((g,1),v[f"fl_{g}"],v[f"fu_{g}"])
                parts.append(("4x1",back,front,v[f"start_{g}"]))
            else:
                product=pair((g,"prod"),v[f"fl_{g}"],v[f"bu_{g}"])
                if v.get(f"next_chain_{g-1}",0) and (g-1)//10==g//10:back=pairids[g-1,"prod"]
                else:back=pair((g,"head"),v[f"dhead_load_{g}"],v[f"dhead_unload_{g}"])
                parts.append(("2x2",back,product,v[f"start_{g}"]))
                if not v.get(f"next_chain_{g}",0):
                    aux=pair((g,"tail"),v[f"dtail_load_{g}"],v[f"dtail_unload_{g}"])
                    parts.append(("2x2",product,aux,v[f"second_{g}"]))
        for q,(mode,back,front,start) in enumerate(parts):
            dt=180 if mode=="4x1" else 90
            carry=bool(q and parts[q-1][2]==back)
            tail=not(q+1<len(parts) and parts[q+1][1]==front)
            rb=cy[-1]["end"] if carry else steps[back][0]+1
            event(f"rot_before_{c}_{q}","rotate",f"CH{c}",None,rb,2,chamber=c,cycle=q)
            if tail:event(f"rot_after_{c}_{q}","rotate",f"CH{c}",None,steps[front][1]+1,2,chamber=c,cycle=q)
            cy.append(dict(chamber=c,index=q,mode=mode,counter=q+1,pairs=[back,front],front=front,start=start,end=start+dt))
    # Identity assignment is interval coloring of actual loans. All dummy wafers are interchangeable.
    last=[-1]*cfg.dummy_count
    for beg,end,p,r,index in sorted(loans):
        slot=next(i for i,val in enumerate(last) if val<=beg)
        last[slot]=end
        label=f"D{slot+1}";pairs[p]["members"][r]=label;series[index]["identity"]=label
    return normalize_schedule(cfg,dict(schema=1,solutions=1,cmax=v["true_C"],config=asdict(cfg),pairs=pairs,jobs=series,events=events,cycles=cy))


def main(file,tag):
    src=Path(file).resolve()
    folder=OUT/"proposals"/tag
    folder.mkdir(exist_ok=True,parents=True)
    doc=reconstruct(read(src))
    attached=attach_hands(doc)
    checks=validate(doc)
    atomic(folder/"decoded.json",doc)
    atomic(folder/"replay.json",dict(source=src.relative_to(JMS).as_posix(),source_sha256=sha(src),
            code_sha256=sha(Path(__file__)),C=doc["cmax"],attached=bool(attached),report=checks))
    if attached and checks["valid"]:
        atomic(folder/f"candidate_{doc['cmax']:g}.json",doc)
        print("Full native-event replay passed",doc["cmax"],flush=True)
    else:
        print("Replay needs native timing repair",doc["cmax"],checks["errors"][:8],flush=True)

if __name__=="__main__":main(sys.argv[1],sys.argv[2])
