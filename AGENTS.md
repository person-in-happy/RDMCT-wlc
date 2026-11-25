# Research project

The current Chinese submission-review source is `JMS-version/JMS_Review_CN.tex`. `JMS/JMS_Review_CN.tex` is a different copy; do not synchronize it implicitly.

For manuscript and experiment review, use `JMS-version/REVIEW_WORKFLOW.md`. Preserve raw results, frozen checkpoints and model hashes. Inspect ongoing experiments read-only unless the user requests intervention. Do not regenerate shared LP paths, restart jobs, or modify their launchers while they are active.

Check scientific claims against the actual objective, model, validation records and comparison budget. A solver timeout without an incumbent is not an infeasibility proof. Keep results requiring unfinished experiments pending until completion and validation.

## Experiment execution preferences (2026-10-16)

For future experiments, run in a visible foreground terminal with live progress, completed/failed counts and an estimated remaining time. Do not launch hidden/background experiments unless the user explicitly requests it again. Prefer parallel independent runs when CPU, RAM and GPU capacity permit; record concurrency and resource settings, keep comparison settings matched, isolate outputs, serialize shared-reference preparation, and avoid simultaneous learned-policy jobs on one GPU by default. Existing frozen campaigns remain read-only unless intervention is requested. Do not change the active serial campaign merely to apply this preference retroactively.

All experiment runners and execution skills must support interruption and resumption by default. Reuse verified endpoints, adopt active workers, restore compatible checkpoints and cumulative budgets, and document the supported recovery granularity. Show elapsed wall time, estimated total and remaining wall time in the foreground and status file, including the estimate's basis and the effects of concurrency. Use a labelled historical estimate before comparable current runs finish when available. Follow the personal `experiment-runner` skill for new campaigns.

## Default Git push target (confirmed by user 2026-11-07)

The user-confirmed project remote is `origin`, URL `https://github.com/person-in-happy/RDMCT-wlc.git`, and the default target branch is `RL-SAT` (`https://github.com/person-in-happy/RDMCT-wlc/tree/RL-SAT`). Use this target for future project push requests unless the user specifies otherwise. Do not ask the user to identify this remote again; verify the local configuration against this record before pushing. This does not authorize force pushes or bypassing approval requirements.

## 默认 PPT 制作技能（用户确认：2026-11-19）

制作、修改和审查 PPT 默认读取 `C:/Users/Administrator/.codex/skills/nature-ppt/SKILL.md`。源副本为 `D:/git/git/nature-skills/skills/nature-ppt/SKILL.md`。遵从用户明确指定的其他技能、语言、模板和格式；学术结果直接按已核验证据陈述，制作汇报不授权重跑或干预实验。
