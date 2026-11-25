# 表3的8片纯配方案例

两组算例均取种子1、4个上料端口、每个端口2片同配方产品、清洁间隔10、虚拟片8、驻留上限100 s。原模型的时间域为100000 s。新实验的工期均指最后一片产品的归还时刻。

各配方的正式入口为 `certified.py`。按以下 PowerShell 命令可在项目根目录续跑，或独立核验已经生成的18个单元格。

```powershell
G:/conda/python.exe -B -u -X utf8 JMS-version/experiments/table3_pure8_20261125/certified.py 4x1
G:/conda/python.exe -B -u -X utf8 JMS-version/experiments/table3_pure8_20261125/certified.py 2x2
G:/conda/python.exe -B -u -X utf8 JMS-version/experiments/table3_pure8_20261125/check_cells.py
```

同一配方的三个A阈值共享一条搜索轨迹。从 SPBS 实际排程出发，两种配方各自采用产品投影的工期下界。产品投影在4×1上求得566 s，在2×2上求得544 s。按投影算法实际找到可行解的先后次序，用其配对、腔室分配和加工周期辅助搜索原模型的可执行排程。每当新排程的真实工期满足尚未交接的阈值，先在原连续模型中回填并回放，再交接到B阶段。每个B使用交接到的离散结构、种子1及指定相对间隙，按当前 Huber 目标重新优化时刻。B的对偶界只适用于该离散结构。

正式数据在 `JMS-version/results/table3_pure8_20261125`。汇总文件 `threshold_cells.csv` 含每格两阶段上下界、实测间隙、排程路径及哈希。`validation.json` 给出原模型独立复核记录。`certified/<配方>/protocol.json` 固化来源与顺序。`projection/<配方>/<cap>/` 保存投影搜索日志及工期界证明。`certified/source_snapshot/candidate.py` 保存生成正式排程时使用的候选搜索代码，哈希可与本次各候选的结果记录核对。

前台控制器显示已完成数、失败数、耗时及剩余估计，并刷新 `certified/<配方>/progress.json`。每配方最多并行三个工作进程，各求解器使用单线程。控制器重启时接管所属存活进程，自动复用哈希核验通过的交接点和B结果。已退出的未完成求解重新建树。A候选保留已交接的阈值，每个候选重启后的90 s预算扣除已记账时间。B阶段没有时间上限，重启后继续以原间隙为终止条件。

使用 `restore_test.py` 可独立测试恢复。它复制8个完成单元格到新建的 `recovery/<时间戳>/`，测试存活进程接管、单格工作进程中止后重算、原8格哈希和最终目标一致性，并写出 `audit.json`。正式结果目录不参与中止测试。

`run.py` 的直接全模型A搜索属于前期试跑，停止记录见 `direct_pilot_stop.json`。正式18格采用上面记录的投影界辅助流程。
