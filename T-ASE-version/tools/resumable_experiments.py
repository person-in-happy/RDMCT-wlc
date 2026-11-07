"""Resumable T-ASE experiments; dry-run unless --execute is supplied.

Keep extra_experiments.py unchanged while its legacy campaign is active.
Resume restarts an interrupted evaluation, not a SCIP search tree.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "T-ASE-version"
DEFAULTS = dict(seeds="1,2,3,4,5", max_instances=0, construction_limit=180.0, device="cuda:0")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_text(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def assert_idle(out, experiment=None):
    # Legacy launchers do not acquire our lock. Detect their parent/child processes.
    target = os.path.normcase(str(out.resolve())).replace("\\", "/").lower()
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process | "
                  "Where-Object { $_.Name -match 'python' } | "
                  "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True, encoding="utf-8", errors="replace")
        entries = json.loads(raw) if raw.strip() else []
        if isinstance(entries, dict):
            entries = [entries]
        processes = [(entry["ProcessId"], entry.get("CommandLine") or "") for entry in entries]
    else:
        raw = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
        processes = [(int(line.split(None, 1)[0]), line.split(None, 1)[1])
                     for line in raw.splitlines() if len(line.split(None, 1)) == 2]
    for pid, command in processes:
        if pid == os.getpid():
            continue
        command = command.replace("\\", "/").lower()
        if "python" not in command:
            continue
        legacy = "extra_experiments.py" in command
        same_kind = experiment is None or experiment in command
        if target in command or (legacy and same_kind):
            raise RuntimeError(
                f"Experiment process {pid} is still active. "
                "Wait for it to exit before executing resume; dry-run is safe."
            )


@contextmanager
def campaign_lock(out):
    # OS lock is released even after a kill/reboot; never delete the lock inode.
    path = out / ".resume.lock"
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another process holds the campaign lock") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def inventory(experiment, commands, files):
    paths = set(ROOT.glob("*.py"))
    paths.update((ROOT / "cie/code").glob("*.py"))
    paths.update((ROOT / "cie/configs").glob("*.json"))
    paths.add(Path(__file__).resolve())
    paths.add(PAPER / "tools/benchmark_resume_guard.py")
    paths.add(PAPER / "tools/extra_experiments.py")
    if experiment == "sensitivity":
        manifest = ROOT / "cie/configs/cie_benchmark_suites.json"
        for suite in read_json(manifest)["suites"]:
            if suite["name"] == "cie_sensitivity":
                folder = (manifest.parent / suite["root"]).resolve()
                paths.update(p for p in folder.rglob("*") if p.is_file())
        for command in commands:
            for flag in ("--hem_model", "--proposed_model"):
                if flag in command:
                    model = Path(command[command.index(flag) + 1])
                    paths.add(model)
                    paths.add(model.with_name("variant.json"))
        paths.add(ROOT / "cie/results/repro_manifest/selected_checkpoint_manifest.csv")
    else:
        for name in files:
            paths.add(Path(name))
            paths.add(Path(name).with_suffix(".cie.json"))
    return {str(p.resolve()): sha(p) for p in sorted(paths) if p.is_file()}


def verify_assets(manifest):
    for name, expected in manifest["assets"].items():
        if not Path(name).is_file() or sha(name) != expected:
            raise RuntimeError(f"Input/code hash changed: {name}. Use a new campaign.")
    current = inventory(manifest["experiment"], manifest["commands"], manifest["files"])
    if current != manifest["assets"]:
        raise RuntimeError("Experiment asset inventory changed. Use a new campaign.")


def make_plan(experiment, options, out):
    commands, files = [], []
    if experiment == "sensitivity":
        # Reuse the original argument builder, without executing any experiment.
        command = [sys.executable, str(PAPER / "tools/extra_experiments.py"), experiment]
        for key, value in options.items():
            command += ["--" + key.replace("_", "-"), str(value)]
        plan = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
        original = Path(plan["output"])
        commands = [[arg.replace(str(original), str(out)) for arg in cmd]
                    for cmd in plan["commands"]]
    else:
        sources = sorted((ROOT / "cie/data/core/spbs").glob("*.lp"))
        if options["max_instances"]:
            sources = sources[:options["max_instances"]]
        if not sources:
            raise RuntimeError("No frozen SPBS instances")
        files = [str(p.resolve()) for p in sources]
    return dict(version=1, experiment=experiment, output=str(out), options=options,
                commands=commands, files=files,
                assets=inventory(experiment, commands, files))


def legacy_sensitivity(out):
    commands = read_json(out / "plan.json")
    if not isinstance(commands, list) or len(commands) != 6:
        raise RuntimeError("Unrecognized legacy sensitivity plan")
    for command in commands:
        if Path(command[1]).resolve() != (ROOT / "cie/code/run_cie_benchmarks.py").resolve():
            raise RuntimeError("Unexpected benchmark executable")
        if "--no_resume" in command:
            raise RuntimeError("Legacy plan disables checkpoint recovery")
        for flag in ("--output_dir", "--solution_dir"):
            Path(command[command.index(flag) + 1]).resolve().relative_to(out)
    # Verify selected model hashes even when adopting a pre-manifest campaign.
    sys.path.insert(0, str(PAPER / "tools"))
    from extra_experiments import checkpoints
    selected = set(checkpoints().values())
    for command in commands:
        for flag in ("--hem_model", "--proposed_model"):
            if flag in command and command[command.index(flag) + 1] not in selected:
                raise RuntimeError("Legacy model is not a frozen selected checkpoint")
    return dict(version=1, experiment="sensitivity", output=str(out), options=None,
                commands=commands, files=[], legacy=True,
                provenance_note="Assets captured at adoption, not at original launch.",
                assets=inventory("sensitivity", commands, []))


def repair_checkpoint_tail(path):
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    offset = 0
    for index, line in enumerate(lines):
        if line.strip():
            try:
                json.loads(line)
            except (ValueError, UnicodeDecodeError):
                if index != len(lines) - 1:
                    raise RuntimeError(f"Corrupt checkpoint interior: {path}")
                # Preserve the entire original; remove only uncommitted tail.
                backup = path.with_name(path.name + ".interrupted_" + uuid.uuid4().hex + ".bak")
                shutil.copy2(path, backup)
                with path.open("r+b") as stream:
                    stream.truncate(offset)
                    stream.flush()
                    os.fsync(stream.fileno())
                return
        offset += len(line)
    if data and not data.endswith(b"\n"):
        with path.open("ab") as stream:
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())


def run_logged(command, log_path):
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\nResume attempt: " + datetime.datetime.now().isoformat() + "\n")
        log.flush()
        child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = child.wait()
        except BaseException:
            # Stop only the child started here. Completed JSONL rows remain reusable.
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            raise
        if code:
            raise subprocess.CalledProcessError(code, command)


def run_sensitivity(out, manifest, runner=run_logged):
    for i, command in enumerate(manifest["commands"]):
        output = Path(command[command.index("--output_dir") + 1])
        print(f"Batch {i + 1}/{len(manifest['commands'])}: reuse evaluation checkpoints", flush=True)
        guarded = [command[0], str(PAPER / "tools/benchmark_resume_guard.py")] + command[2:]
        runner(guarded, out / f"job_{i}.log")
        # A runner may exit 0 after recording evaluation errors. Do not call it complete.
        checkpoints = list((output / ".checkpoints").glob("*.jsonl"))
        complete = []
        for path in checkpoints:
            records = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
            complete.extend(r for r in records if r.get("record_type") == "complete"
                            and all(Path(p).is_file() for p in r.get("artifacts", []))
                            and r.get("artifacts"))
        if not complete:
            raise RuntimeError(f"Batch {i} has unfinished/error evaluations; inspect job_{i}.log and resume.")
    for name, extra in [
        ("analyze_cie_solutions.py", ["--validate", "--fail_on_invalid"]),
        ("analyze_cie_submission.py", ["--stage", "sensitivity", "--no_plots"]),
    ]:
        runner([manifest["commands"][0][0], str(ROOT / "cie/code" / name),
                "--input_dir", str(out / "runs"), "--output_dir", str(out / "analysis")] + extra,
               out / "analysis.log")
    atomic_json(out / "complete.json", {"experiment": "sensitivity", "status": "complete"})


def save_records(out, rows):
    atomic_json(out / "records.json", rows)
    if rows:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        atomic_text(out / "records.csv", buffer.getvalue())


def run_spbs(out, manifest, construct=None, validate=None, config_factory=None):
    if construct is None:
        sys.path.insert(0, str(ROOT))
        from petri_mip_generator import PetriMIPConfig
        from petri_warm_start import write_mixed_warm_start
        from cie.code.analyze_cie_solutions import _validate
        construct, validate, config_factory = write_mixed_warm_start, _validate, PetriMIPConfig
    rows = read_json(out / "records.json") if (out / "records.json").exists() else []
    options = manifest["options"]
    seeds = [int(v) for v in options["seeds"].split(",")]
    expected = {(name, seed) for name in manifest["files"] for seed in seeds}
    done = set()
    for row in rows:
        key = (row["source_instance"], row["seed"])
        if key not in expected or key in done:
            raise RuntimeError("Unexpected or duplicate SPBS checkpoint item")
        if row["sha256"] != manifest["assets"][row["source_instance"]]:
            raise RuntimeError("SPBS record input hash mismatch")
        if row["has_solution"]:
            if not row["valid"]:
                raise RuntimeError("Saved solution failed validation; fix model compatibility before a NEW campaign.")
            solution = Path(row["solution"])
            if not solution.is_file() or sha(solution) != row["solution_sha256"]:
                raise RuntimeError("Saved SPBS solution missing/changed; inspect evidence before continuing.")
        done.add(key)
    save_records(out, rows)  # Repair CSV if interruption followed JSON commit.
    for name in manifest["files"]:
        source = Path(name)
        cfg = config_factory(**read_json(source.with_suffix(".cie.json"))["config"])
        for seed in seeds:
            if (name, seed) in done:
                print(f"Skip completed: {source.name} seed={seed}", flush=True)
                continue
            # Each retry gets its own directory; interrupted artifacts stay intact.
            case = out / "cases" / source.stem / f"seed_{seed}" / ("attempt_" + uuid.uuid4().hex[:12])
            case.mkdir(parents=True, exist_ok=False)
            frozen = case / source.name
            shutil.copy2(source, frozen)
            expected_hash = manifest["assets"][name]
            if sha(frozen) != expected_hash:
                raise RuntimeError("Input changed before construction")
            start = time.perf_counter()
            solution = construct(str(case), source.name, cfg,
                                 time_limit=options["construction_limit"],
                                 memory_limit_mb=2048, random_seed=seed)
            constructed = time.perf_counter()
            valid, note = validate(frozen, Path(solution)) if solution else (
                False, "No incumbent within construction budget")
            elapsed = time.perf_counter() - start
            if sha(source) != expected_hash or sha(frozen) != expected_hash:
                raise RuntimeError("Input changed during construction")
            row = dict(source_instance=name, sha256=expected_hash, seed=seed,
                       construction_wall_s=constructed-start,
                       construction_plus_validation_wall_s=elapsed,
                       has_solution=bool(solution), valid=bool(valid),
                       validation_note=note, solution=str(solution) if solution else None,
                       solution_sha256=sha(solution) if solution else None,
                       attempt_dir=str(case))
            rows.append(row)
            save_records(out, rows)
            print(json.dumps(row), flush=True)
            if solution and not valid:
                raise RuntimeError("Generated solution failed frozen-model validation; stop and inspect compatibility.")
    atomic_json(out / "complete.json", {"experiment": "spbs-cost", "items": len(rows)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", choices=["sensitivity", "spbs-cost"])
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--resume", type=Path, help="Reuse a saved campaign; options are restored automatically")
    target.add_argument("--output-dir", type=Path, help="New campaign directory, must not already exist")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--seeds")
    parser.add_argument("--max-instances", type=int)
    parser.add_argument("--construction-limit", type=float)
    parser.add_argument("--device")
    args = parser.parse_args(argv)
    supplied = {key: getattr(args, key) for key in DEFAULTS if getattr(args, key) is not None}
    if args.resume and supplied:
        parser.error("--resume restores frozen options; do not supply experiment option overrides")
    if args.resume:
        out = args.resume.resolve()
        if (out / "campaign.json").exists():
            manifest = read_json(out / "campaign.json")
            if manifest["version"] != 1 or manifest["experiment"] != args.experiment:
                parser.error("Campaign type/version mismatch")
            if Path(manifest["output"]).resolve() != out:
                parser.error("Campaign moved; absolute solution/checkpoint paths must be preserved")
            verify_assets(manifest)
        elif args.experiment == "sensitivity" and (out / "plan.json").exists():
            manifest = legacy_sensitivity(out)
        else:
            parser.error("No resumable campaign metadata. Legacy SPBS records do not preserve full options; "
                         "validation failures require compatibility investigation, not resume.")
    else:
        options = DEFAULTS | supplied
        try:
            seeds = [int(value) for value in options["seeds"].split(",")]
        except ValueError:
            parser.error("Seeds must be comma-separated integers")
        if not seeds or len(set(seeds)) != len(seeds):
            parser.error("Use distinct seeds")
        if options["max_instances"] < 0 or not (0 < options["construction_limit"] < float("inf")):
            parser.error("Invalid experiment limit")
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out = (args.output_dir or PAPER / "results" / f"{args.experiment}_{stamp}").resolve()
        if out.exists():
            parser.error("Output exists; use --resume for saved campaigns")
        manifest = make_plan(args.experiment, options, out)
    print(json.dumps({k: v for k, v in manifest.items() if k != "assets"}, indent=2), flush=True)
    print("Resume with: " + subprocess.list2cmdline([
        sys.executable, str(Path(__file__).resolve()), args.experiment,
        "--resume", str(out), "--execute"]), flush=True)
    if not args.execute:
        return
    assert_idle(out, args.experiment)
    if not args.resume:
        out.mkdir(parents=True, exist_ok=False)
    with campaign_lock(out):
        if not (out / "campaign.json").exists():
            atomic_json(out / "campaign.json", manifest)
        verify_assets(manifest)
        if manifest["experiment"] == "sensitivity":
            run_sensitivity(out, manifest)
        else:
            run_spbs(out, manifest)


if __name__ == "__main__":
    main()

