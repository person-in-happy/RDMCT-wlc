# Research project

The current Chinese submission-review source is `JMS-version/JMS_Review_CN.tex`. `JMS/JMS_Review_CN.tex` is a different copy; do not synchronize it implicitly.

For manuscript and experiment review, use `JMS-version/REVIEW_WORKFLOW.md`. Preserve raw results, frozen checkpoints and model hashes. Inspect ongoing experiments read-only unless the user requests intervention. Do not regenerate shared LP paths, restart jobs, or modify their launchers while they are active.

Check scientific claims against the actual objective, model, validation records and comparison budget. A solver timeout without an incumbent is not an infeasibility proof. Keep results requiring unfinished experiments pending until completion and validation.

## Experiment execution preferences (2026-10-16)

For future experiments, run in a visible foreground terminal with live progress, completed/failed counts and an estimated remaining time. Do not launch hidden/background experiments unless the user explicitly requests it again. Prefer parallel independent runs when CPU, RAM and GPU capacity permit; record concurrency and resource settings, keep comparison settings matched, isolate outputs, serialize shared-reference preparation, and avoid simultaneous learned-policy jobs on one GPU by default. Existing frozen campaigns remain read-only unless intervention is requested. Do not change the active serial campaign merely to apply this preference retroactively.

## Default Git push target (confirmed by user 2026-11-07)

The user-confirmed project remote is `origin`, URL `https://github.com/person-in-happy/RDMCT-wlc.git`, and the default target branch is `RL-SAT` (`https://github.com/person-in-happy/RDMCT-wlc/tree/RL-SAT`). Use this target for future project push requests unless the user specifies otherwise. Do not ask the user to identify this remote again; verify the local configuration against this record before pushing. This does not authorize force pushes or bypassing approval requirements.
