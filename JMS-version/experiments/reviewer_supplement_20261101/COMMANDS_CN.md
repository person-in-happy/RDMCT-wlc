# 审稿问题对应的定向补充实验

本入口读取已完成且通过物理验证的排程，输出到新的结果目录。原求解器、原始实验与文稿保持原样。正式实验尚未启动。

## 可直接执行的三组

| 顺序 | Suite | 要回答的问题 | 数量与预算 |
|---|---|---|---|
| 1 | `cleanup` | 保留已有产品完工时间及二阶段目标上界后，末端辅助片归还和装载锁恢复能否提前完成？ | 42份已报告的完整二阶段排程，每份后处理60 s |
| 2 | `baseline` | 固定结构为何比联合搜索更好？把固定结构优化用于初始解后，联合搜索能否改进？ | 4种实例×3种方法×3种子＝36组；每组设定总求解预算300 s |
| 3 | `rhythm` | 长链、实际清洁及混合配方中，节拍项及其权重是否仍有效？ | 3种实例×4个权重×3种子＝36组；共同第一阶段排程，每组精修60 s |

设置路径和新批次名：

```powershell
Set-Location D:\git\git\RDMCT-A3C
$r = '.\JMS-version\experiments\reviewer_supplement_20261101\run_review.ps1'
$tag = Get-Date -Format 'yyyyMMdd_HHmmss'
$cleanup = ".\JMS-version\results\review_cleanup_$tag"
$baseline = ".\JMS-version\results\review_baseline_$tag"
$rhythm = ".\JMS-version\results\review_rhythm_$tag"
```

按顺序逐条运行，当前终端显示完成数、失败数、内存和剩余时间估计：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite cleanup -Campaign $cleanup -MemoryMB 6000 -ProcessMemoryMB 7000 -CleanupLimit 60
```

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite baseline -Campaign $baseline -MemoryMB 6000 -ProcessMemoryMB 7000 -TimeLimit 300
```

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite rhythm -Campaign $rhythm -MemoryMB 10000 -ProcessMemoryMB 14000 -Stage2Limit 60
```

三组共114份最终结果；其中强基线包含12次固定结构预求解，共126次求解器调用。预算和实际耗时分别记录，建模与结果保存还需时间，不把求解预算相加当作实际总用时。均为单进程、单求解线程；前两组要求可用内存至少9048 MiB，节拍组要求至少16048 MiB。

## 比较口径

### 收尾后处理

取基础实验24份、资格实验6份、原节拍实验12份 `refined` 最终排程。固定全部离散选择，分别给产品回片完工时间和完整二阶段加权目标加上原值上界，在此条件下最小化已建模动作、腔室周期以及装载锁复位的最晚结束时刻。数值上界容差为1e-6 s/目标单位，验解容差为2e-4。

这是对已有输出的收尾选择，不重新定义产品完工时间，也不向原等待集合添加腔内等待项。它保留的是二阶段加权目标上界，并不逐项保证总等待、最大等待和节拍偏差均不增。结果分别报告这些指标及全部已建模工作的完工时刻；通过原模型约束和物理事件重放后才记为完成。收尾变化的结论由新输出确定。

### 强初始解对照

实例为4片和8片、H=3和H=10、双源混合配方。每个实例复用同一份历史SPBS初始赋值，比较：

- `joint`：联合求解300 s。
- `fixed`：固定参考结构，优化时序和可释放的资源次序300 s。
- `fixed_then_joint`：先固定结构求解60 s，再把所得完整赋值作为联合求解起点，联合求解240 s。

三个方法的设定求解预算相同。预求解包含在第三种方法的300 s中，历史共享SPBS准备成本另行说明；SCIP实际停止可能超过设定时间，各阶段实际耗时和建模耗时均保留。固定结构的下界只属于相应受限子问题，不能与联合问题的下界混用。

这一组检查“强初始解是否解决联合搜索起点较弱的问题”，不等于已经证明联合搜索优于固定结构。新结果需与初始值、最终值和下界一起解释。

### 节拍项与权重

直接读取已完成阈值实验的第一阶段完整赋值，同一实例、同一种子下四个权重使用同一文件及哈希，不重新运行第一阶段：

| 实例 | 有效节拍评价点 | 实际清洁次数 |
|---|---:|---:|
| 16片、H=10、纯2×2、双源 | 6 | 0 |
| 24片、H=5、纯2×2、双源 | 8 | 2 |
| 24片、H=5、混合配方、双源 | 2 | 2 |

精修目标为 `总路线等待 + 10×最大路线等待 + λ×节拍偏差`，其中 `λ∈{0,5,25,100}`。λ=0是去掉节拍项的消融。固定第一阶段离散结构与资源次序，仅放开连续时刻和原精修阶段允许变化的同步动作开关，并保留产品完工时间上界。

三个实例按链长、清洁与混合配方机制选取，属于定向机制检验；三个种子属于同一实例的重复运行。该组不复用原来“无实际清洁”的48条节拍运行作为新增证据，也不做线性目标与未归一化二次目标的直接权重比较。

## 查看、恢复和检查

仅查看计划，不建模、不求解：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Action plan -Suite rhythm
```

查看批次进度：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Action status -Campaign $rhythm
```

恢复已有批次时，沿用冻结设置，不再传入 `-Suite` 或内存、时间参数：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Action resume -Campaign $rhythm
```

检查失败日志并解决原因后，显式重新尝试失败单元，旧尝试会存档：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Action resume -Campaign $rhythm -RetryFailed
```

如果需要改变资源或时间预算，应使用新批次名重新 `start`，不能修改已冻结批次。内存不足且尚未开始的批次可以在释放内存后直接 `resume`。

输出为 `summary/cells.csv`、`summary/coverage.json`、各运行的 `result.json`、`evidence.json`、求解日志和内存记录。`complete` 表示获得通过验解的结果；是否达到当前子问题最优值另看 `solver_status`，不把可行限时解记作完整问题的最优解。

## 仍缺少可执行实现的一项

**相同FIFO规则下的逐片/Pjob表示对照仍需实现。** 当前旧逐片求解器与批次求解器的跨LP顺序规则不一致，直接运行旧模型会同时改变可行域，不能用来单独证明批次表示减少变量、节点和求解时间。

这项对照应对齐产品、配方、资格、跨LP严格出片、同批次禁止同时取片、候选配对/周期容量、初始物理排程和求解预算，再比较变量/约束/非零元数量、建模内存时间、首个可行解和最终界。当前入口没有该实验，`scale`、`core`或旧模型命令也不能替代它。本说明不为尚未实现的对照编造命令。

产品/辅助片等待分项、初始与最终值、已有运行时间分解可以从现有数据重算；不需要再次运行整套216次阈值实验，也无需为这些汇总另跑学习选割实验。
