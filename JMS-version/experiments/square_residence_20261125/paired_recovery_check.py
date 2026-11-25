"""Interrupt a separate short native run; verify the recovered cumulative budget and physical endpoint."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import paired_rerun as runner

def worker(base):
    # Test-only duration. The publication trial uses the complete seed-specific budget.
    ref=base/"reference"
    timing=runner.read(runner.OUT/"reference2/timing.json")
    timing=dict(timing,total_s=16.,recovery_test=True)
    runner.store(ref/"timing.json",timing)
    runner.paired.original.solve=runner.paired.Method()
    runner.paired.original.load_reference=runner.reference
    runner.paired.metrics=runner.metrics
    runner.paired.objective_terms=runner.objective_terms
    trial=runner.Trial(2,"no_spbs",base/"run",ref)
    trial.observed=set()
    runner.store(base/f"boot{trial.s['attempt']}.json",dict(attempt=trial.s["attempt"],charged=trial.offset,start=trial.key["start"]))
    trial.run()

def main():
    with tempfile.TemporaryDirectory(prefix="rdmct_square_recovery_") as tmp:
        base=Path(tmp)
        cmd=[sys.executable,"-B","-X","utf8",str(Path(__file__).resolve()),str(base)]
        with (base/"worker.log").open("w",encoding="utf8") as log:
            first=subprocess.Popen(cmd,stdout=log,stderr=log)
            pulse=base/"run/clock.json"
            try:
                for step in range(75):
                    if first.poll() is not None:
                        raise RuntimeError("First test worker ended before its checkpoint")
                    if pulse.is_file() and runner.read(pulse)["charged_s"]>=3:
                        break
                    time.sleep(1)
                else:
                    raise TimeoutError("Checkpoint unavailable")
            finally:
                if first.poll() is None:first.terminate()
                first.wait()
            before=runner.read(pulse)["charged_s"]
            second=subprocess.run(cmd,stdout=log,stderr=log)
        if second.returncode:
            raise RuntimeError((base/"worker.log").read_text(encoding="utf8")[-2200:])
        boot=runner.read(base/"boot2.json")
        result=runner.read(base/"run/result.json")
        assert runner.read(base/"boot1.json")["start"]==boot["start"]==result["key"]["start"]
        assert before<=boot["charged"]<16
        assert result["observed_s"]==16 and result["used_s"]==16
        endpoint=runner.read(base/"run/endpoint/primary.json")
        assert endpoint["replay"]["valid"] and endpoint["rows"]>0
        doc=dict(test_budget_s=16,checkpoint_charged_s=before,resumed_charged_s=boot["charged"],
                 final_charged_s=result["used_s"],same_start_sha256=boot["start"],checked_native_rows=endpoint["rows"],
                 scope="Isolated actual SCIP interruption; never used in the statistical comparison.")
        runner.store(runner.OUT/"recovery_test.json",doc)
        print(doc,flush=True)

if __name__=="__main__":
    if len(sys.argv)==2:worker(Path(sys.argv[1]))
    else:main()
