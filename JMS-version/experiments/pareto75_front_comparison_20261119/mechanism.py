"""Independent mechanism checks on fresh seeds after the shared-population comparison."""
from pathlib import Path
import json
import random
import time
from case_setup import HERE, OUT, CASES, NFE, ROOT, Search, digest, read, save, save_schedule, signature
from paired import execute, spec
from trial import Trial, founders, exported

MOUT=HERE/"results/mechanism01"
MSEEDS=tuple(range(301,313))
ARMS=("full","no_blocks","random_init")
M_WORKERS=4


class Mechanism(Trial):
    def __init__(self,case,seed,arm):
        super().__init__(case,seed,"domain")
        self.arm=arm
        # Initial random structures use independent random variates. The main
        # search in all arms starts with the identical proposal RNG state.
        init=random.Random(10000+seed)
        self.initial_structures=[tuple(init.randrange(v) for v in self.limits) for _ in range(6)]

    def evaluate(self,genes,goal,cap,screen,end):
        before=self.stats["evaluations"]
        assert before<NFE and self.remaining(end)>1
        if before<12 and self.arm=="random_init":
            genes=self.initial_structures[before//2]
        if before>=12 and self.arm=="no_blocks":
            if any(genes[1:]):
                self.stats["projected_block_moves"]+=1
            genes=(genes[0],0,0,0)
        self.inside=True
        try:
            value=Search.evaluate(self,genes,goal,cap,screen,end)
        finally:
            self.inside=False
        count=self.stats["evaluations"]
        if count<=12:
            self.starting_records.append([tuple(genes)+(17 if goal=="A" else 0,),value])
        if count in (12,40,80,160):
            self.checkpoints[count]=sorted(self.archive)
        return value


def cells():
    rng=random.Random(3012026)
    groups=[(c,s) for c in CASES for s in MSEEDS]
    rng.shuffle(groups)
    result=[]
    for c,s in groups:
        methods=list(ARMS)
        rng.shuffle(methods)
        result.extend((c,m,s) for m in methods)
    return result


def contract():
    return dict(primary="Separate follow-up cohort and hypothesis family: compare full vs no_blocks and full vs random_init within each workload. HV7 using exactly the previous scaling. Six structured founders or six random admissible genotypes (feasibility screened by decoder), two endpoints each and 148 subsequent evaluations. Disable block edits by projecting any local proposal onto the same global family with three zero block handles. Keep long-visit sampling, caps, family changes, archive and LP identical. Shared RNG for subsequent search, separately seeded RNG for random initialization.",
        analysis="Four exact two-sided paired sign tests Holm-adjusted over both workloads and both ablations. Seedwise median HV differences and exact median intervals; full-archive HV sensitivity. Fixed sample. Conclusions here apply to mechanisms, independently of the six algorithm comparisons.",
        cases=CASES,seeds=MSEEDS,methods=ARMS,evaluations=NFE,workers=M_WORKERS,threads=1,
        parent_protocol_sha256=digest(OUT/"protocol.json"),source_sha256=digest(Path(__file__)),
        original_code=spec()["sha256"])


def run_cell(job):
    c,arm,seed=job
    trial=Mechanism(c,seed,arm)
    elapsed=trial.run("domain",900)
    assert trial.stats["evaluations"]==NFE
    if arm=="no_blocks":
        assert all(not any(genes[1:]) for genes,_,_ in trial.archive.values())
    folder=MOUT/c/f"{arm}_{seed}"
    folder.mkdir(parents=True,exist_ok=True)
    selected=set(exported(trial.archive))
    entries=[]
    for (a,b),(genes,data,found) in sorted(trial.archive.items()):
        sig=signature(data)
        obj=folder/(sig+".json.gz")
        save_schedule(obj,data)
        entries.append(dict(a=a,b=b,genes=genes,sig=sig,file=obj.name,found_s=found,submitted=(a,b) in selected))
    save(folder/"run.json",dict(case=c,method=arm,seed=seed,warm=trial.initial_ab,stats=trial.stats,cap=NFE,
         archive=entries,start=trial.starting_records,checkpoints=trial.checkpoints,trace=trial.trace,elapsed_s=elapsed))
    return len(entries)


def main():
    MOUT.mkdir(parents=True,exist_ok=True)
    path=MOUT/"protocol.json"
    frozen=json.loads(json.dumps(contract()))
    if path.exists():
        assert read(path)==frozen
    else:
        save(path,frozen)
    import paired
    # This process has its own status file and terminal; original search and
    # original audits keep reporting to their existing files.
    def status(message):
        print(message,flush=True)
        with (MOUT/"progress.log").open("a",encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ")+message+"\n")
    paired.log=status
    todo=[j for j in cells() if not (MOUT/j[0]/f"{j[1]}_{j[2]}"/"run.json").exists()]
    status(f"Mechanism cohort | {len(todo)}/72 cells | 4 CPU workers, 1 thread each | 160 evaluations")
    execute("mechanism search",todo,run_cell,lambda j,result:None,M_WORKERS,50)
    assert all((MOUT/c/f"{m}_{s}"/"run.json").exists() for c,m,s in cells())
    assert read(path)==json.loads(json.dumps(contract()))
    save(MOUT/"finished.json",dict(cells=72,source_match=True))
    status("MECHANISM SEARCH COMPLETE 72/72")


if __name__=="__main__":
    main()
