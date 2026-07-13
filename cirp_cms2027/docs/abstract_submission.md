# CIRP CMS 2027 摘要初稿

目标提交日期：2026-09-11。官网尚未在公开页面说明摘要字数限制，粘贴前应以投稿系统字段为准。

## Title

Executable Scheduling of a Dual-Source Rotary Cluster Tool

## Abstract

Rotary semiconductor cluster tools are often scheduled at chamber level, although actual throughput also depends on single-slot alignment, robot repositioning, load-lock capacity, auxiliary-wafer availability, and cleaning. We study a manufacturing cell in which product wafers and reusable process-enabling carrier (PEC) wafers enter from different stores and share an atmospheric robot, a vacuum robot, two load locks, and two rotary chambers. The cell supports a four-wafer batch recipe and a two-pair exchange recipe. We formulate a finite-horizon mixed-integer scheduling model that represents loaded and empty robot motion, explicit load-lock slots, serial alignment, chamber-side rotations, PEC conservation, and cleaning within an exchange chain. A structure-preserving binary-skeleton procedure supplies feasible initial schedules without restricting the original optimization problem. Recorded validation solves reproduce both pure recipes and expose a sharp computational difficulty increase under mixed production. The final study will compare no warm start and two skeleton profiles across recipe ratios, PEC inventories, cleaning intervals, and unseen lot sizes, reporting makespan, time to first feasible schedule, optimality gap, and ATR/VTR/chamber utilization. The intended outcome is an auditable scheduling method in which the Gantt chart serves as an executable equipment certificate rather than only a chamber ordering.

## Keywords

Semiconductor manufacturing; cluster tool; production scheduling; mixed-integer optimization; manufacturing systems.

## 提交前检查

- 根据系统字数限制压缩；
- 填入作者和单位；
- 确认摘要提交是否必须以及能否在全文阶段修改题目；
- 不写任何尚无正式对照实验支撑的百分比；
- 若 INCOM 稿件已经送审，不再提交高度重合的 CMS 全文。

