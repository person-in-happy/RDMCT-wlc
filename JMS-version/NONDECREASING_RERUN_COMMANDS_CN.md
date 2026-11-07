# 非递减出片规则：补跑范围与可执行命令（2026-11-02）

当前文稿：`JMS-version/JMS_Review_CN.tex`。新后端：`model4_pjob_nondecreasing_20261102`。
本次已准备独立代码、入口与验证；没有启动正式实验。旧代码、活动队列、冻结结果和策略权重保持原样。

## 先明确哪些结论可以保留

严格出片可行域包含于非递减出片可行域。旧排程仍是可行排程，其实际完工时间、等待等指标仍可描述该排程；旧模型的最优值、下界、求解时间、内存、成功率及方法排名不能直接作为新模型结果。

- 若只保留“旧排程的可行性/已有构造族下界”，无需重新优化，但引用时必须注明原规则；这些序列不是新模型的全部可行序列。
- 若把现稿的定量实验统一更新为非递减规则，需要下面的对应组。现稿仍包含阈值图、32片表、8片目标消融和学习选割数值；旧命令文档称阈值/32片“可选”的判断已不适用于当前稿件。
- 已有42份收尾结果固定了全部离散选择，包括同步开关，可以继续作为旧排程后处理的结果保留。若要展示新排程的收尾效果，必须在新主实验完成并验解后，使用新的源批次重新后处理。
- 旧的完整赋值可以作新模型的共同可行起点。下面定向比较默认复用历史不可变起点，两臂/各权重保持相同输入哈希；它们衡量“共同历史起点下的新规则搜索/精修”，不冒称从新主阶段自动生成的端到端结果。

## 补跑清单

| 组 | Suite / 入口 | 数量 | 何时需要 |
|---|---|---:|---|
| 小规模表示一致性 | followup / exact | 16次主求解 + 8项公共起点补全 | 优先验证新规则；新增同Pjob同LP的2片4×1、2×2实例 |
| 基础主实验 | main / paper | 102 | 更新初始化、基础精修、小规模模式及固定结构结果 |
| 资格与编码 | main / qualification | 6 | 更新资格实验数值；仅保留旧可行见证则不必重算 |
| 8片目标消融 | main / rhythm | 48 | 保留原8片线性/二次/仅等待目标比较时 |
| 逐片/Pjob表示 | strengthen / representation | 36 | 更新模型规模、RSS与300 s求解比较 |
| 强起点/固定结构对照 | review / baseline | 36 | 更新 joint/fixed/fixed_then_joint 比较 |
| 长链与清洁节拍权重 | review / rhythm + strengthen / rhythm_memory | 24 + 12 | 更新36组权重结果；24片纯链式只跑代入实现，不重复 |
| 公平准备计时 | followup / timing | 72次测量，不优化 | 新矩阵改变，准备时间需重新测量；6实例×2表示×6次 |
| 学习选割 | main / paper_cuts | 72 | 现稿保留该段数值则补跑；使用原冻结策略，不重新训练 |
| 清洁阈值扫描 | main / crossover | 216 | 现稿阈值图与相关数值更新必须补跑 |
| 32片规模 | main / scale32 | 9 | 三种配方×三种子；不重演旧内存失败批次 |
| 驻留压力 | followup / residency | 6 | 若继续此前待补实验，应直接采用新规则 |
| 双腔并行见证 | followup / parallel | 3 | 两片分别属于不同Pjob，同批规则对此实例不生效；已有有效物理见证可保留，没有见证时继续完成 |
| 新排程收尾 | review / cleanup | 通常42 | 读取新paper/qualification/rhythm的refined输出；缺失或未验证时不把预期数当完成数 |

不需要因为这次规则修正重做全部旧core、ablation、DOE、OOD或策略训练。对照预算在各自实验组内匹配，不将不同起点批次的结果混合排名。

## 前台运行命令

在项目根目录的可见PowerShell中设置路径，以下命令按组逐条执行。各入口自动创建带时间戳的新目录，显示完成/失败数和ETA；不要启动隐藏窗口，也不要同时启动多个控制队列。

```powershell
Set-Location 'D:\git\git\RDMCT-A3C'
$m = '.\JMS-version\model4_pjob_nondecreasing_20261102\run_experiments.ps1'
$r = '.\JMS-version\experiments\nondecreasing_review_20261102\run_review.ps1'
$s = '.\JMS-version\experiments\nondecreasing_strengthening_20261102\run_strengthen.ps1'
$f = '.\JMS-version\experiments\nondecreasing_followup_20261102\run_followup.ps1'
```

先做小规模新规则对照。600 s是每个主求解预算；超时无可行解不等于不可行，两臂未同时证明最优时不宣称等值最优。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $f -Suite exact -TimeLimit 600
```

主实验及8片目标消融，最多两个独立CPU任务并行，每个SCIP单线程；共享参考准备由控制器串行完成。默认主预算300 s，精修方法270+30 s，SPBS另计20 s。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Suite paper -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Suite qualification -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Suite rhythm -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
```

定向表示、强起点及节拍比较。`representation`保留原300 s预算；`baseline`的混合方法仍为60+240 s；长链各权重60 s。后面两个rhythm命令合计36项，两个入口的`rhythm`含义不同，勿混用。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $s -Suite representation -TimeLimit 300 -MemoryMB 10000 -ProcessMemoryMB 14000
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Suite baseline -TimeLimit 300 -MemoryMB 6000 -ProcessMemoryMB 7000
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Suite rhythm -Stage2Limit 60 -MemoryMB 10000 -ProcessMemoryMB 14000
powershell -NoProfile -ExecutionPolicy Bypass -File $s -Suite rhythm_memory -Stage2Limit 60 -MemoryMB 10000 -ProcessMemoryMB 14000
powershell -NoProfile -ExecutionPolicy Bypass -File $f -Suite timing
```

保留现稿的学习选割、阈值和32片数值时，继续以下三组。学习策略最多占用一个GPU槽位；无需训练新策略，结论限定于冻结策略在新规则模型上的表现。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Suite paper_cuts -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Suite crossover -Jobs 1 -MemoryMB 10000 -ProcessMemoryMB 14000
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Suite scale32 -Jobs 1 -MemoryMB 12288 -ProcessMemoryMB 18432
```

新阈值组统一使用10000/14000 MiB，32片三种配方统一使用12288/18432 MiB，不沿用历史中途改变内存预算的混合配置；因此不要据此直接声称相对历史严格规则的耗时/内存改善。32片须有足够空闲内存，资源门槛不满足时保留批次并按冻结设置恢复，不取消保护。

待补的驻留压力与并行见证：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $f -Suite residency -TimeLimit 300 -Stage2Limit 60
powershell -NoProfile -ExecutionPolicy Bypass -File $f -Suite parallel -TimeLimit 600
```

新排程收尾依赖前三个主实验批次。下面三个路径必须替换为新入口启动时打印的实际目录；不设置这些参数时，入口默认处理历史排程，不能当作新主实验的收尾。

```powershell
$paper = 'JMS-version/results/替换为新的paper批次目录'
$qualification = 'JMS-version/results/替换为新的qualification批次目录'
$rhythm = 'JMS-version/results/替换为新的主入口rhythm批次目录'
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Suite cleanup -PaperCampaign $paper -QualificationCampaign $qualification -RhythmCampaign $rhythm -CleanupLimit 60 -MemoryMB 6000 -ProcessMemoryMB 7000
```

## 只检查、不启动正式实验

本次已完成测试。需要复核时可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File '.\JMS-version\model4_pjob_nondecreasing_20261102\run_validation.ps1'
```

该脚本包含10项有20 s/1024 MiB上限的小规模正确性测试及18项禁止`optimize()`的入口检查；不是正式比较实验。两种配方、两种表示的同步见证固定已知物理结构，只证明该同步排程可行，不证明完整主问题全局最优。

查看补充组计划（只检查输入与数量）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $f -Action plan -Suite exact
powershell -NoProfile -ExecutionPolicy Bypass -File $s -Action plan -Suite representation
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Action plan -Suite rhythm
```

## 状态、恢复与验收

将`$entry`设置为创建该批次的入口（`$m/$r/$s/$f`之一）；`$campaign`使用启动时打印的实际目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $entry -Action status -Campaign $campaign
powershell -NoProfile -ExecutionPolicy Bypass -File $entry -Action resume -Campaign $campaign
```

恢复时不再传Suite、源批次或资源预算。需要改变预算时建新批次。补充入口的失败单元只有诊断后加`-RetryFailed`才重试；旧尝试保留。主入口的`audit`命令为：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $m -Action audit -Campaign $campaign
```

验收必须核对数量、运行退出状态、完整原模型验解、独立物理重放，以及`release_order_rule=global_pjob_index_nondecreasing_lp_pickup`或批次`model=pjob_global_nondecreasing_v1`。小规模精确对照看`summary/exact_pairs.json`的`both_optimal`及`equal_proven_values`。未完成、无incumbent、限时可行、已证最优分别报告；不把`finished.json`或退出码0直接当作科学验证通过。

## 实现差异

- 跨LP边界从前一LP的取片结束时刻改为取片开始时刻。
- 删除同Pjob同对的同步禁令；同地点、物理手、动作互斥和换位条件保留。
- 两套逐片对照构造器均把相邻取片约束改为非递减，不再增加`atr_handling`间隔。
- 独立顺序检查接受相等时间，拒绝逆序；物理验证仍拒绝跨LP同步和不同对的ATR冲突。
- 同时取片按时间、LP、对、成员位确定编码。逐片身份与规范解码可以在同任务、同LP、同取片时刻内置换；显式选择仍保存，非同刻或跨任务/LP置换拒绝。
- 新代码、新输出标记与冻结清单独立；历史33个源文件哈希核对保持不变。
