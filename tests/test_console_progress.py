from __future__ import annotations

import io
import json
import sys

import run_petri_a3c_beam as petri_runner


def test_petri_child_output_goes_to_log_not_console(tmp_path, capsys):
    log_file = tmp_path / "solver.log"
    status_file = tmp_path / "status.json"
    progress_stream = io.StringIO()
    command = [
        sys.executable,
        "-c",
        (
            "import sys; "
            "print('child stdout detail'); "
            "print('child stderr detail', file=sys.stderr)"
        ),
    ]

    petri_runner._run(
        command,
        status_file=str(status_file),
        heartbeat_seconds=0.05,
        max_wall_seconds=5.0,
        log_file=str(log_file),
        console_mode="progress",
        progress_file=progress_stream,
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert "Petri A3C+Beam" in progress_stream.getvalue()
    detail = log_file.read_text(encoding="utf-8")
    assert "child stdout detail" in detail
    assert "child stderr detail" in detail
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["return_code"] == 0

def test_petri_wrapper_redirects_setup_details(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace

    args = SimpleNamespace(
        instance_dir=str(tmp_path),
        instance_name="wrapper-smoke.lp",
        detailed_log_file="",
        console_mode="progress",
    )
    monkeypatch.setattr(petri_runner, "_parse_args", lambda: args)

    def fake_execute(runtime_args, progress_file):
        print("wrapper setup detail")
        petri_runner.logger.log("wrapper structured detail")
        progress_file.write("PETRI PROGRESS\n")
        progress_file.flush()

    monkeypatch.setattr(petri_runner, "_execute", fake_execute)

    petri_runner.main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "PETRI PROGRESS\n"
    wrapper_log = tmp_path / "runtime_wrapper-smoke_wrapper.log"
    detail = wrapper_log.read_text(encoding="utf-8")
    assert "wrapper setup detail" in detail
    assert "wrapper structured detail" in detail