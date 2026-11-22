"""Complete interrupted cells, preserving the original campaign and every failed attempt."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys
import time

from campaign import fingerprints, loads
from common import HERE, ROOT, digest, save


def retry_cell(out, ident, dest):
    from search import Search
    import neighborhood
    import native

    # Keep the frozen call, limits, and parent selection. An invalid numerical
    # incumbent contributes zero schedules, just as a subproblem without an incumbent.
    class CheckedNative(native.Native):
        def query(self, goal, cap, screen, parents, deadline):
            try:
                return super().query(goal, cap, screen, parents, deadline)
            except ValueError as exc:
                if str(exc) != "SCIP returned an invalid incumbent":
                    raise
                return [], dict(goal=goal,cap=cap,scope="unrestricted",nodes=0,warm=0,
                                status="candidate_rejected_original_rows",nodes_available=False)
    native.Native = CheckedNative
    neighborhood.Native = CheckedNative
    spec = next(s for s in loads(out/"protocol.json")["cells"] if s["id"] == ident)
    Search(spec, dest, out/"shared_initials").run()


def complete(out):
    protocol = loads(out/"protocol.json")
    first = loads(out/"finished.json")
    if protocol["code"] != fingerprints() or not first["sources_match"]:
        raise ValueError("Frozen solver source differs from its manifest")
    if digest(protocol["policy"]["checkpoint"]) != protocol["policy"]["sha256"]:
        raise ValueError("Frozen policy differs from its manifest")
    done = dict(first["done"])
    recovered = {}
    # Reject other failures explicitly; they need their own diagnosis.
    for ident, entry in first["failed"].items():
        err = loads(out/entry["path"]/"error.json")
        if "ValueError: SCIP returned an invalid incumbent" not in err["error"]:
            raise ValueError(f"{ident}: {err['error']}")
    def work(ident):
        root = out/"recovery"/ident
        root.mkdir(exist_ok=True,parents=True)
        for result in sorted(root.glob("attempt_*/result.json")):
            if loads(result)["spec"]["id"] == ident:
                return result
        dest = root/f"attempt_{len(list(root.glob('attempt_*')))+1:02d}"
        dest.mkdir()
        with (dest/"worker.log").open("w",encoding="utf-8") as f:
            subprocess.run([sys.executable,"-B","-X","utf8","-u",str(Path(__file__).resolve()),
                            str(out),"--cell",ident,"--dest",str(dest)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
        return dest/"result.json"
    remaining = list(first["failed"])
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(work, k):k for k in remaining}
        for future in as_completed(tasks):
            ident = tasks[future]
            result = future.result()
            url = result.relative_to(out).as_posix()
            recovered[ident] = dict(original_failure=first["failed"][ident],completed=url)
            done[ident] = url
            elapsed = time.monotonic()-start
            print(f"补跑完成 {len(recovered)}/{len(remaining)} | {ident} | 预计剩余 "
                  f"{elapsed*(len(remaining)-len(recovered))/len(recovered):.1f}s",flush=True)
    final = dict(done=done,total=first["total"],failed={},sources_match=True,recovered=recovered,
                 frozen_protocol_sha256=digest(out/"protocol.json"),first_run_sha256=digest(out/"finished.json"),
                 recovery_code_sha256=digest(Path(__file__)),
                 rule="same seed, budget and common starting schedules; an incumbent failing original SCIP rows is discarded")
    save(out/"completed_for_audit.json",final)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    parser.add_argument("--cell")
    parser.add_argument("--dest",type=Path)
    args=parser.parse_args()
    if args.cell:
        retry_cell(args.out.resolve(),args.cell,args.dest.resolve())
    else:
        complete(args.out.resolve())
