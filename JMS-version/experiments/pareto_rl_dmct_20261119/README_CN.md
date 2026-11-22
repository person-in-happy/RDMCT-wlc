# 晶圆组合设备的双目标调度实验

本目录包含独立的算法入口、调度解码器、实验运行器和评估程序。模型 D、SPBS 初始化、独立设备事件校验和冻结学习选割检查点均从原路径导入。运行结果写入本目录的 runs 子目录。原论文和原实验的运行入口可以继续使用。

## 目标与搜索

两个目标均最小化。A 是最后一片产品返回原端口的时刻。B 是全部晶圆沿路线的额外等待总量，加上最大单项等待的 10 倍和节拍偏差的 25 倍。排程解码允许产品同配，也允许产品与真空辅助片配对。可改变分配腔室、两片的取放顺序和不同生产块竞争共享设备的先后次序。

对固定产品数和产品配对数，求解器由设备时序计算等待下界，提前放弃无法满足当前 B 上限的配对结构。通过上限的候选进入固定资源顺序的连续时刻线性规划。下一阶段在混合整数子问题中释放一部分取放次序，再调用原始全模型上的 ε 约束子问题。每个拟加入档案的候选都在整例时限内复核设备事件、未缩减模型 D 的原始约束和模型目标值。运行结束后，评估程序从磁盘重放每份最终排程。

- [目标、设备工况和配对下界](common.py) · [离散结构与连续时刻解码](decoder.py)
- [档案、ε 上限与邻域搜索](search.py) · [同规模顺序变量释放](neighborhood.py)
- [原模型求解与选割](native.py) · [把实际事件还原为原模型变量](witness.py)
- [NSGA-II 与 MOEA/D 的选择和更新](evolution.py) · [共同初始化及计费](initials.py)

NSGA-II 与 MOEA/D 参照本机 PlatEMO 的 MATLAB 实现编写，使用同一套整数排程表示和 LP 解码。每个方法独立占用一个 CPU 求解线程。学习版沿用原检查点，预算包含该次加载和初始化。原两阶段算法作为单份排程对照。配对下界和松弛哪些物理资源是本项目研究的算法机制。

## 正式工况与对照

| 实验 | 输入与设置 |
|---|---|
| 六种算法主比较 | 两片 S1、四片混合 M4、配方为 3+1 的四片 H4、八片混合 H8、十六片混合 H16。各有三个种子，单次预算依次为 40、45、45、55、80 秒 |
| 增加时间预算 | S1 上六种方法均用 300 秒、种子 1 重新求解 |
| 消融 | S1 和 M4 比较普通与领域邻域、配对下界开关、对内取放次序变异和自适应等待上限。对内变异消融保持后端 SCIP 修复及其预算一致 |
| 配对子问题 | 同父排程、同目标、同上限、同数量的释放变量。两种策略各三个种子，18 秒 |
| 算法参数 | M4 的变量释放比例为 0.15、0.30、0.50，修复阶段预算占比为 0.12、0.22、0.32。每次仅变动一个参数，扰动取两个种子 |
| 设备参数 | 四片混合把辅助片库存从 8 改为 4，或把清洁阈值从 10 改为 3，各自重新排程 |
| 节拍权重 | 八片纯 2×2 工况 R8，权重取 0、12.5、25、50，比较领域搜索与 NSGA-II，各有两个种子 |

S1 的独立认证前沿只由评估程序读入。主比较的归一化、预算、初始输入、随机种子、解释器及依赖版本记录在实验清单中。中大实例的前沿图展示每种算法 HV 中位数对应的一次运行。另存各运行的坐标和跨方法、跨种子的经验非支配点。不同目标权重分别计算指标，同一交付期限下的工期与等待分量用于跨权重比较。

## 在 Windows 前台复现

从仓库根目录在 PowerShell 运行以下命令。为新运行选择新的目录名。正式比较使用 formal02。首轮 formal01 保留了局部清洁排程导致原模型与物理指标不一致的诊断记录及当时的九个源文件快照。下列命令使用本机已准备好的 a3cenv。

~~~powershell
$module = 'JMS-version/experiments/pareto_rl_dmct_20261119'
$pythonPareto = 'G:/conda/envs/a3cenv/python.exe'
& $pythonPareto -B -X utf8 -m unittest discover -s $module -p test_pareto.py -v
& $pythonPareto -B -X utf8 "$module/campaign.py" prepare "$module/runs/repeat01" --workers 6
& "$module/foreground.ps1" -Campaign repeat01 -Workers 6
& "$module/evaluation_foreground.ps1" -Campaign repeat01
~~~

前台控制台持续显示完成数、失败数、剩余时间和可用内存。每个实例与种子的共同初始排程只串行制备一次，初始化的实际耗时计入每种方法的整例预算。评估程序仅为因原始约束拒绝候选而中止的组启用相同配置的补跑，保留原始尝试。补跑会舍弃未通过原始约束的候选。求解器超时状态和各方法触发学习选割的次数均可逐次核对。

[正式实验清单](runs/formal02/protocol.json) · [数值复验与实验报告](runs/formal02/evaluation/report_CN.md) · [逐条件与种子文件](runs/formal02/evaluation/runs.csv) · [首轮问题实例](runs/formal01/evaluation/audit_failure.json)

## 两片生产阶段补充实验

[活动配对结构的时序精修](active_phase.py)分别固定两片产品同配和各自配一片辅助片、分配到不同腔室的结构。生产阶段开放机器人次序。构造排程给出搜索上限，每找到一个解就收紧等待指标上限。重建强制末端清洁后再逐份检查原模型，单独记录运行时间和可行排程。该实验使用实例专用结构，耗时与四种规模的同预算主比较分别记录。

~~~powershell
& $pythonPareto -B -X utf8 -u "$module/active_phase.py" "$module/runs/s1_polish_repeat" --seconds 150
& $pythonPareto -B -X utf8 -u "$module/split_refinement.py" "$module/runs/s1_polish_repeat" "$module/runs/s1_refine_repeat" --seconds 150
& $pythonPareto -B -X utf8 "$module/score_special.py" "$module/runs/s1_refine_repeat"
~~~

第二步从前一步的真实排程确定目标上限，在既有两片专用时序模型适用的区域枚举双腔室曝光次序，使用原模型重新分配辅助片并恢复末端清洁。它复用了既有小实例验证器的结构知识。独立证书和参考目标向量在第三步才进入逐点评分。[本次重算的完整前沿图](runs/s1_refine01/s1_complete_CN.png) · [七个排程与逐点误差](runs/s1_refine01/front_checked.csv)

## 配对下界的单独对照

固定 S1 或 M4、目标上限、原始可行解和求解器种子，在未缩减模型上分别开启和关闭配对计数约束。每次分配 4 秒给子问题。记录模型准备时间、实际节点数、界、停止状态及核验后的条件工期。该实验共 12 对。[直接消融结果](runs/cut_pairs01/paired.csv)

~~~powershell
& $pythonPareto -B -X utf8 -u "$module/epsilon_ablation.py" "$module/runs/formal02" "$module/runs/cut_pairs_repeat" --seconds 4
~~~
