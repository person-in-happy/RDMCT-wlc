# 100片排程：持续求解、可行解出图与原路径更新（2026-11-11）

当前使用 [large_schedule_experiments_v2.py](tools/large_schedule_experiments_v2.py)。它保留“可行解出图、改进后更新原路径、证明完成后更新最优标注”，并增加用户要求的**关闭RAM余量保护**模式。旧入口large_schedule_experiments.py及旧结果原样保留。

严格模式不设求解时间、墙钟时间、节点数或解数量上限，只有完整主问题证明全局最优且100片/两模式/清洁验证通过才记为成功。旧协议三次触发25%余量保护；无保护批次随后实际运行315.25 s，在构模时遇到SCIP真实内存分配失败，尚未进入优化。当前两类批次都没有100片可行排程。

## 最新操作：已扩容分页文件并在可见终端续跑

2026-11-11 13:52（中国标准时间）已完成：D盘分页文件初始64 GiB、最大128 GiB，C盘仍按驱动器系统管理。D盘已实际分配64 GiB，系统提交上限实测98.35 GiB，未重启即已生效。原无保护批次已执行`resume --retry-failed`，13:52:48核验时仍在构模，暂无可行排程。可见终端PID为32224，本次日志为`foreground_1794376322117148000.log`；旧失败记录已归档保留。当前仍运行时不要再次执行启动或续跑命令。详见[运行时核验](review/large_schedule_allocation_failure_20261111/pagefile_runtime_verification.json)。

## 扩容前失败：保护已关闭，系统仍无法分配构模内存

详见[本次诊断与分页文件处理步骤](review/large_schedule_allocation_failure_20261111/README.md)和[机器可读证据](review/large_schedule_allocation_failure_20261111/diagnosis.json)。本次不是GPU显存不足或25%保护触发：

| 已核实项目 | 结果 |
|---|---|
| 内存保护 | memory_guard_enabled=false；guard_snapshot=null |
| 失败位置 | model.py:454，resources()中添加机器人事件排序约束 |
| 底层错误 | SCIP扩容307957024 bytes（293.69 MiB）失败 |
| 运行时间/工作进程驻留峰值 | 315.25 s / 22.12 GiB |
| 整机提交峰值/最后记录的提交上限 | 50.28 GiB / 50.43 GiB |
| 最低物理可用内存 | 约168 MiB，0.517% |
| 可行解/甘特图 | 均没有；构模未完成 |

整机提交峰值与最后上限样本不一定同时，不能用两者的差值断言失败指令那一瞬间的精确余量。现有日志与采样支持提交容量紧张的判断；进一步关闭脚本保护没有作用。通用提示中的“saved incumbents and Gantt retained”不代表本次已经生成过排程，实际目录中没有这些文件。

已在空闲较多的D盘增加分页文件，避免完全依赖C盘的小初始分页文件运行时增长；自动增长本身也可能来不及满足大块申请，见[微软说明](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/slow-page-file-growth-memory-allocation-errors)。64/128 GiB初始/最大容量的设置与实际验证已写入上述诊断，不是充分容量保证，也不是给实验固定RAM配额。

以后调整分页文件后，先检查提交上限是否实际增大（本次已验证生效，不需要先重启）：

~~~powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$large = 'JMS-version/tools/large_schedule_experiments_v2.py'
$campaign = 'JMS-version/results/n100_H3_mixed_dual_no_ram_guard_20261111_r1'
& $py -X utf8 -u $large check --campaign $campaign
~~~

check输出memory_snapshot.system_commit_limit_bytes为当前系统提交上限（字节）。也可在任务管理器“性能→内存→已提交”查看已用量/上限；之前该任务记录的上限约50.43 GiB。GPU预检通过并不验证剩余容量一定足够100片构模。

资源条件改善且该目录没有工作进程运行后，使用下面命令重新构模；不再prepare，也不使用run：

~~~powershell
& {
    Set-Location D:\git\git\RDMCT-A3C
    $py = 'G:\conda\envs\a3cenv\python.exe'
    $large = 'JMS-version/tools/large_schedule_experiments_v2.py'
    $campaign = 'JMS-version/results/n100_H3_mixed_dual_no_ram_guard_20261111_r1'
    & $py -X utf8 -u $large check --campaign $campaign
    if ($LASTEXITCODE -ne 0) { throw '预检失败，未启动续跑。' }
    & $py -X utf8 -u $large resume --campaign $campaign --retry-failed
}
~~~

仅重复相同资源配置无法解决已确认的分配失败。完整模型最后究竟需要多少内存仍未测得；增加分页文件可能很慢，也可能仍不足。本次已更改Windows分页文件设置并续跑，冻结代码、输入、检查点与原始失败记录保留。

## 无保护协议的首次启动方式（当前批次已续跑，见上节）

最初旧协议的报错来自管理进程主动终止：即使还剩约8 GiB RAM，也会因为低于25%而停止。v2关闭这一保护后，本次已遇到上节所述真实分配失败。

新协议使用--no-memory-guard，冻结为memory_guard_enabled=false、min_available_fraction=0、memory_policy=native_unlimited_observe_only。SCIP/RSS均无固定内存配额，主求解仍不设时间或节点上限。**可用RAM低于25%、10%或更低时都不会被此保护终止；提交额度紧张也只提示。** Windows仍可能因无法分配内存而让工作进程失败，不能保证“不够也一定跑完”。

下面是可见PowerShell中的首次启动模板，只有目录确实不存在时才prepare；已准备时跳过prepare。当前目录已在扩容后续跑，此模板仅供以后使用，不能与当前运行同时执行。

~~~powershell
& {
    Set-Location D:\git\git\RDMCT-A3C
    $py = 'G:\conda\envs\a3cenv\python.exe'
    $large = 'JMS-version/tools/large_schedule_experiments_v2.py'
    $campaign = 'JMS-version/results/n100_H3_mixed_dual_no_ram_guard_20261111_r1'

    if (-not (Test-Path -LiteralPath $campaign)) {
        & $py -X utf8 -u $large prepare --campaign $campaign --size 100 --recipe mixed --cleaning-interval 3 --dummy-count 8 --method proposed --training-seed 1 --seed 1 --gpu-device 0 --until-optimal --no-memory-guard
        if ($LASTEXITCODE -ne 0) { throw '准备失败，未启动求解。' }
    }
    & $py -X utf8 -u $large check --campaign $campaign
    if ($LASTEXITCODE -ne 0) { throw '预检失败，未启动求解。' }
    if (Test-Path -LiteralPath "$campaign/solve") {
        & $py -X utf8 -u $large status --campaign $campaign
        throw '已有运行记录。正在运行时不要重启；失败或中断后使用下面的新批次续跑命令。'
    }
    & $py -X utf8 -u $large run --campaign $campaign
}
~~~

确认check输出memory_guard_enabled=false、min_available_fraction=0.0。启动后应看到MEMORY_GUARD_DISABLED。以后内存紧张时显示MEMORY_PRESSURE_CONTINUING，含义是提示后继续；这不是失败退出。

新批次的状态、绘图与续跑使用新入口和新目录：

~~~powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$large = 'JMS-version/tools/large_schedule_experiments_v2.py'
$campaign = 'JMS-version/results/n100_H3_mixed_dual_no_ram_guard_20261111_r1'
& $py -X utf8 -u $large status --campaign $campaign

# 以下命令按需单独执行，不要在仍运行时重复启动
# & $py -X utf8 -u $large resume --campaign $campaign --retry-failed
# & $py -X utf8 -u $large render --campaign $campaign
~~~

--no-memory-guard只在prepare/start时设置并冻结；不能给旧目录的resume临时追加来改变原协议。v2也支持--min-available-fraction 0表达关闭保护。旧入口及其25%协议未修改，所以不要再用旧$large/$campaign来运行此次无保护实验。

## 原因、分页文件及验证边界

扩容前检查时物理RAM约31.72 GiB，Windows已启用自动管理分页文件，C盘分页文件当时分配2688 MiB（2.625 GiB），并非其固定最大值；C盘空闲约68.34 GiB。当时实际读取的系统提交上限约34.35 GiB，会随分页文件增长变化。新增D盘分页文件后上限实测98.35 GiB。新入口每10秒报告RAM_available与system_commit=已用/当前上限，并把系统提交峰值和RAM余量写入resources.json。后台模型仍只建立一份。

Windows可以用分页文件支持部分超出物理RAM的已提交内存，但增长受系统和磁盘条件限制；大量换页会使运行变慢，提交空间耗尽后仍可能分配失败。参见[微软分页文件说明](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/how-to-determine-the-appropriate-page-file-size-for-64-bit-versions-of-windows)。新入口使用[GetPerformanceInfo的提交统计](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-performance_information)，不把物理空闲RAM等同于系统还能提交的内存。本次已调整系统分页文件，未重启机器。

模型本身的内存需求较大也有代码依据：550个候选PW对×2个腔室×300个候选周期，仅占位变量就有330000个，另有首次占位、产品占位、腔室前侧变量及大量约束；机器人事件和资源占用还建立两两排序关系。Python表达式、字典与SCIP约束同时占用内存。GPU用于后续选割推理，不能承担这些构模对象。该结构解释了内存增长，但本次没有测出完整100片模型的最终RAM需求。

63项检查通过，包含旧/新入口的全局最优验收和甘特图更新检查，以及模拟仅剩1% RAM、提交额度99%时无保护模式继续运行、原25%模式仍拦截。真实GPU预检通过，记录在新目录preflight_check.json。此处低内存测试使用模拟计数，不耗尽真实机器内存，也不代表100片求解已经成功。

## 旧25%保护协议的报错与结果（保留参考）

两条报错都是目录保护：Output exists表示重复prepare；Incomplete attempt retained表示对失败目录使用run。正确的失败续跑操作为resume --retry-failed。GPU预检已经通过，代码、输入和策略仍与冻结协议匹配。

已检查n100_H3_mixed_dual_until_optimal_live_20261111_r1的三次实际运行：

| 尝试 | 运行时间 | 采样峰值RSS | 停止时整机可用内存 | 停止原因 |
|---|---:|---:|---:|---|
| 首次运行 | 88.36 s | 10.65 GiB | 7.80 GiB，24.58% | system_available_memory_guard |
| resume续跑 | 87.17 s | 10.44 GiB | 7.89 GiB，24.86% | system_available_memory_guard |
| 再次resume | 108.34 s | 12.91 GiB | 7.93 GiB，25%以下 | system_available_memory_guard |

整机总内存约31.72 GiB，旧协议要求可用量至少25%。这是整机剩余量保护，不是给求解器固定10.65 GiB配额。三次均无build.json和termination_settings.json，仅有构模开始日志；尚未进入主优化，且没有latest_incumbent.json，因此没有排程或甘特图。最新一次实际余量为24.9969%，格式化后会接近25%，但仍低于保护阈值。

上述旧协议检查时无100片求解进程在运行；最新续跑状态见本文开头。资源条件未改善时，不建议继续重复同一命令。GPU选割推理在构模之后，不能解除构模内存瓶颈；也不能从这些停止记录推断实例不可行或算出完成构模需要多少RAM。

| 目录状态 | 操作 |
|---|---|
| 不存在 | prepare → check → run |
| 已准备，尚无solve目录 | check → run |
| 已有失败或中断的solve目录 | 查看失败原因；条件改善后check → resume --retry-failed |
| 同目录仍在运行 | 查看日志和status，不重复启动 |
| 已证全局最优完成 | status / render，不重跑 |

**下面仅用于保留25%保护的旧协议；本次取消保护应使用本文开头的v2新批次。** 不重新prepare、不删除旧目录；重试重新构模，不恢复搜索树。

~~~powershell
& {
    Set-Location D:\git\git\RDMCT-A3C
    $py = 'G:\conda\envs\a3cenv\python.exe'
    $large = 'JMS-version/tools/large_schedule_experiments.py'
    $campaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r1'

    & $py -X utf8 -u $large check --campaign $campaign
    if ($LASTEXITCODE -ne 0) { throw '预检失败，未启动续跑。' }
    & $py -X utf8 -u $large resume --campaign $campaign --retry-failed
    if ($LASTEXITCODE -ne 0) { throw '本次尝试未完成，请查看上方原因及solve/failure.json。' }
}
~~~

此前两次运行的复核数据见[followup_diagnosis.json](review/large_schedule_failure_20261111/followup_diagnosis.json)。本轮另建v2及无保护协议；旧冻结代码和失败记录原样保留。

## 已核对的现有结果与命令

当前检查的 journal_d_transfer_20261109_r1 冻结为432个单元、6个实例，全部为2片。初始可行解搜索虽预设2/4/8片，进入transfer的通过可行性验证的输入排程只有2片。原期刊清单的mechanism最多4片、qualification最多8片、chain为4/6片，后续rhythm依赖已有小实例。学位论文清单也没有所需的100片完整主问题。

旧100片约9998 s排程违反当前100 s非加工驻留约束，不能作为当前D结果。文稿已换入完整模型复验通过的16片纯4×1、Cmax=920 s可行排程，未证全局最优，全资源占用到938 s；此图不含清洁，不能代替100片混合加工与清洁实验。

## 100片实例及全局最优的范围

100片产品：50片4×1、50片2×2；LP1/LP2各13片4×1及12片2×2，LP3/LP4各12片4×1及13片2×2。两个Pjob均可进入CH2/CH3；采用当前非递减投片规则、双源、8片辅助库存、100 s非加工驻留及承片上限、10000 s含复位时域。4×1加工180 s，2×2每次90 s，清洁500 s，H=3。

完整候选域为550个PW对、每腔300个周期，max_pairs=max_cycles=0。不固定配对、分腔或清洁结构，不加见证约束。证明目标是完整主问题的产品回片Cmax；固定结构或二阶段的optimal不能充当这个主问题的全局最优。

清洁由原模型强制：产品曝光总需求为50+2×50=150，每个满片周期最多4次产品曝光，至少需要38个生产周期。设清洁数为K，两腔末尾各至多H−1=2个生产周期，每次清洁之前至多H=3个周期，因此38≤3K+4，K≥12。这证明任何可行排程均含清洁，不证明10000 s时域内必有可行解。

## 旧25%协议：首次运行或已准备但尚未运行（保留参考）

在另一个可见PowerShell终端执行。只增加一个100片工作进程，输出独立，不占原journal队列锁，不修改或重启已有实验。

~~~powershell
& {
    Set-Location D:\git\git\RDMCT-A3C
    $py = 'G:\conda\envs\a3cenv\python.exe'
    $large = 'JMS-version/tools/large_schedule_experiments.py'
    $campaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r1'

    if (Test-Path -LiteralPath "$campaign/solve") {
        & $py -X utf8 -u $large status --campaign $campaign
        throw '已有运行记录。失败目录请用上节续跑命令；正在运行或已完成时不要重复启动。'
    }
    if (-not (Test-Path -LiteralPath $campaign)) {
        # 只对新目录准备；失败即退出整个脚本块
        & $py -X utf8 -u $large prepare --campaign $campaign --size 100 --recipe mixed --cleaning-interval 3 --dummy-count 8 --method proposed --training-seed 1 --seed 1 --gpu-device 0 --until-optimal --min-available-fraction 0.25
        if ($LASTEXITCODE -ne 0) { throw '准备失败，未启动求解。' }
    }

    # 已准备目录直接预检；此步不构建100片模型
    & $py -X utf8 -u $large check --campaign $campaign
    if ($LASTEXITCODE -ne 0) { throw '预检失败，未启动求解。' }
    & $py -X utf8 -u $large run --campaign $campaign
    if ($LASTEXITCODE -ne 0) { throw '运行未完成，请查看停止原因，不要重新prepare。' }
}
~~~

同一目录只prepare一次。脚本块中的局部变量不带到其他命令块，独立查看状态前重新设置$py、$large、$campaign。调整协议需要新目录。不要把--until-optimal与--time-limit或--wall-limit同时使用。已有目录的GPU预检通过，只说明策略和参数可加载，不表示100片模型能装入内存。

每10 s显示完成/失败数、耗时、进程RSS和整机可用内存比例，最优性完成时间显示optimality_ETA=unknown。SCIP与BLAS各用单线程，Windows使用较低CPU优先级；这里的并行是新旧工作进程同时运行。

## 自动更新的是哪些文件

得到更好的incumbent后，先检查完整原始MILP赋值和独立物理时序，再保存到incumbents/000001等独立快照目录。完整结果、全部变量和证书写完后才原子更新latest_incumbent.json；中途停止不会让指针指向半份结果。

前台管理进程自动调用独立绘图子进程，更新同一组文件：

- figures/gantt_resources.pdf、gantt_resources.png、gantt_resources.svg：完整资源甘特图，显示加工、清洁、搬运及装载锁复位。
- figures/wafer_routes.pdf：全部产品及辅助身份的逐片路线分页图。
- figures/figure_evidence.json、manifest.json：覆盖情况、来源快照、验证结论和哈希。

未证最优时，图注明“已验证可行，未证全局最优”；证明完成后，同一路径改为“产品完工已证全局最优”。更差的解不会覆盖更好的图。快速连续改善时绘图可合并为最近的最好解，全部已提交快照仍保留。图中Cmax对应产品回片，辅助片收尾及装载锁复位可能更晚。

刷新图片或重新载入PDF即可查看更新。若PDF查看器占用文件导致无法替换，会提示GANTT_UPDATE_PENDING并记录plot_*.log；关闭占用文件后自动重试。求解已停止时，可用下面的render命令重试。每个文件采用临时文件替换，manifest最后发布；发生文件占用时，以最后完整发布的manifest为准。

尚未找到通过验证的可行解时不会出图。此自动更新针对新campaign的固定图路径，不会把未完成的100片结果自动写进论文正文，也不会修改正在运行的旧实验。

## 旧协议的状态和手动更新（新协议见开头命令）

运行过程中或停止后均可在另一个终端执行：

~~~powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$large = 'JMS-version/tools/large_schedule_experiments.py'
$campaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r1'
& $py -X utf8 -u $large status --campaign $campaign

# 默认允许已验证但未证最优的排程；从最近完整快照更新原路径
& $py -X utf8 -u $large render --campaign $campaign

# 仅检查并导出已证全局最优的100片排程；未证最优时此命令会拒绝
& $py -X utf8 -u $large render --campaign $campaign --require-optimal
~~~

最优验收要求：100片产品、实际4×1/2×2/clean周期、完整原始赋值与物理重放通过、完整候选域、主目标为产品回片Cmax、主问题status=optimal、有效上下界闭合且gap为零，并验证结果、赋值和协议哈希。SCIP数值容差下的最优性证明不等同于有理数精确证明。

## 旧协议的资源保护、重试和GPU（新协议只观察内存）

不设固定SCIP内存或进程RSS配额，limits/memory保留原生无限标记。每0.5 s监测整机可用内存；低于总物理内存25%时，输出RESOURCE_INSUFFICIENT和实际剩余量，仅停止新求解进程。内存/显存/磁盘分配失败也会提示并保留日志。动态保护不能保证操作系统绝不会在两次采样之间耗尽内存。

已提交的最好排程及已有图继续保留；停止后尝试完成最新快照的绘图。尚在验证或写入的最后一次改善可能来不及提交，之前的完整快照不受影响。无可行解时不存在可保留的甘特图。已证不可行显示PROVEN_INFEASIBLE；其他未完成证明显示PROOF_INCOMPLETE或具体失败原因，不记成“最优成功”。

解决资源问题后，执行本文开头包含变量设置的续跑命令。对当前已两次因内存余量停止的目录，不建议直接反复重试。

旧solve目录归档到interrupted_attempts；已保存快照不改写，自动载入最近最好赋值作为初始解。重试重新构模，不恢复分支定界树。内存不足时立即重试相同配置通常仍会停止。

若修改方法、GPU或保护比例，应建新campaign。使用同实例最好赋值热启动：

~~~powershell
& {
    Set-Location D:\git\git\RDMCT-A3C
    $py = 'G:\conda\envs\a3cenv\python.exe'
    $large = 'JMS-version/tools/large_schedule_experiments.py'
    $campaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r1'
    if (-not (Test-Path -LiteralPath "$campaign/latest_incumbent.json")) {
        throw '该目录尚无已保存可行解，不能热启动。'
    }
    $best = Get-Content "$campaign/latest_incumbent.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    $warm = Join-Path $campaign "$($best.snapshot)/variables.json"
    $nextCampaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r2'
    if (Test-Path -LiteralPath $nextCampaign) { throw '目标目录已存在，请使用新的目录名。' }

    & $py -X utf8 -u $large prepare --campaign $nextCampaign --size 100 --recipe mixed --cleaning-interval 3 --dummy-count 8 --method proposed --training-seed 1 --seed 1 --gpu-device 0 --until-optimal --min-available-fraction 0.25 --warm-start $warm
    if ($LASTEXITCODE -ne 0) { throw '准备失败，未启动求解。' }
    & $py -X utf8 -u $large check --campaign $nextCampaign
    if ($LASTEXITCODE -ne 0) { throw '预检失败，未启动求解。' }
    & $py -X utf8 -u $large run --campaign $nextCampaign
    if ($LASTEXITCODE -ne 0) { throw '运行未完成，请查看停止原因。' }
}
~~~

仅在latest_incumbent.json已存在时使用热启动命令，16片赋值不能热启动100片实例。

检查时机器为20逻辑处理器、约31.7 GiB RAM和单张RTX 5060 Ti（8151 MiB显存）。此前32片完整表示已有内存停止记录，100片可能在构模完成前触发保护。取消时间上限不能解决构模内存瓶颈。

proposed使用冻结策略在GPU上选割；模型构建、LP和分支定界主要使用CPU/RAM。本次实际GPU载入预检成功。共享同一GPU会争用显存和计算时间，增加GPU占用不能替代MILP所需RAM。入口采用单个SCIP模型；SCIP并发求解需要相应接口和构建支持，不能仅把线程参数调大就视作已启用，见[官方求解接口](https://www.scipopt.org/doc-9.2.3/html/group__PublicSolveMethods.php)。

此任务用于寻找排程及证明最优，资源争用和无时间上限均影响比较口径，不能并入原300 s等时算法对照。

## 旧入口验证与未完成项

24项自动检查通过，覆盖错误最优声明拒绝、100片50/50完整范围、无时间/节点上限、真实SCIP小模型回调、快照提交及重试、未证最优出图、相同路径改善与最优标注更新，以及严格模式下未完成证明不能计为成功。真实回调测试只解微型测试模型，不是正式排程实验。

已有16片完整赋值另行通过新发布流程检查，177905个变量逐项保存后与原值一致，物理验证通过，并生成实际资源及逐片路线图；此检查不调用优化。

旧入口交付前的最终严格模式GPU预检记录在results/large_schedule_preflight_20261111_r4，明确model_built=false、solver_started=false；旧预检原样保留。用户随后启动的100片旧r1三次触发25%余量保护；v2无保护批次又在构模时发生SCIP实际内存分配失败。两者均没有可行解，100片可行性和全局最优仍未验证；不能截断候选域后把局部最优改称全局最优。
