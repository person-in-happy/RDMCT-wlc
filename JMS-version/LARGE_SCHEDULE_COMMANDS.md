# 100片排程：持续求解、可行解出图与原路径更新（2026-11-11）

新增入口 [large_schedule_experiments.py](tools/large_schedule_experiments.py) 已支持：**找到已验证的可行排程就出图；每次找到更优排程自动更新同一路径；证明全局最优后更新图中文字。** 不需要等证明完成才查看排程。

严格模式不设求解时间、墙钟时间、节点数或解数量上限，只有完整主问题证明全局最优且100片/两模式/清洁验证通过才记为成功。无法保证现有硬件必能完成证明，也不能保证指定实例必然可行；资源不足、已证不可行和证明未完成会分别提示。本次没有启动正式100片构模或优化。

## 已核对的现有结果与命令

当前检查的 journal_d_transfer_20261109_r1 冻结为432个单元、6个实例，全部为2片。资格搜索虽预设2/4/8片，进入transfer的合格输入只有2片。原期刊清单的mechanism最多4片、qualification最多8片、chain为4/6片，后续rhythm依赖已有小实例。学位论文清单也没有所需的100片完整主问题。

旧100片约9998 s排程违反当前100 s非加工驻留约束，不能作为当前D结果。文稿已换入完整模型复验通过的16片纯4×1、Cmax=920 s可行排程，未证全局最优，全资源占用到938 s；此图不含清洁，不能代替100片混合加工与清洁实验。

## 100片实例及全局最优的范围

100片产品：50片4×1、50片2×2；LP1/LP2各13片4×1及12片2×2，LP3/LP4各12片4×1及13片2×2。两个Pjob均可进入CH2/CH3；采用当前非递减投片规则、双源、8片辅助库存、100 s非加工驻留及承片上限、10000 s含复位时域。4×1加工180 s，2×2每次90 s，清洁500 s，H=3。

完整候选域为550个PW对、每腔300个周期，max_pairs=max_cycles=0。不固定配对、分腔或清洁结构，不加见证约束。证明目标是完整主问题的产品回片Cmax；固定结构或二阶段的optimal不能充当这个主问题的全局最优。

清洁由原模型强制：产品曝光总需求为50+2×50=150，每个满片周期最多4次产品曝光，至少需要38个生产周期。设清洁数为K，两腔末尾各至多H−1=2个生产周期，每次清洁之前至多H=3个周期，因此38≤3K+4，K≥12。这证明任何可行排程均含清洁，不证明10000 s时域内必有可行解。

## 与当前实验并行的前台命令

在另一个可见PowerShell终端执行。只增加一个100片工作进程，输出独立，不占原journal队列锁，不修改或重启已有实验。

~~~powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$large = 'JMS-version/tools/large_schedule_experiments.py'
$campaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r1'

# 冻结100片完整模型和持续求解协议；此步不构模、不优化
& $py -X utf8 -u $large prepare --campaign $campaign --size 100 --recipe mixed --cleaning-interval 3 --dummy-count 8 --method proposed --training-seed 1 --seed 1 --gpu-device 0 --until-optimal --min-available-fraction 0.25

# 检查冻结策略、GPU和终止参数；此步不构建100片模型
& $py -X utf8 -u $large check --campaign $campaign
if ($LASTEXITCODE -ne 0) { throw '预检失败，先查看提示，不启动求解。' }

# 前台运行；新可行解和改进解自动保存、验证、更新甘特图
& $py -X utf8 -u $large run --campaign $campaign
~~~

同一目录只prepare一次；已准备的目录直接check/run。调整协议需要新目录。不要把--until-optimal与--time-limit或--wall-limit同时使用。

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

## 状态和手动更新

运行过程中或停止后均可在另一个终端执行：

~~~powershell
& $py -X utf8 -u $large status --campaign $campaign

# 默认允许已验证但未证最优的排程；从最近完整快照更新原路径
& $py -X utf8 -u $large render --campaign $campaign

# 仅检查并导出已证全局最优的100片排程；未证最优时此命令会拒绝
& $py -X utf8 -u $large render --campaign $campaign --require-optimal
~~~

最优验收要求：100片产品、实际4×1/2×2/clean周期、完整原始赋值与物理重放通过、完整候选域、主目标为产品回片Cmax、主问题status=optimal、有效上下界闭合且gap为零，并验证结果、赋值和协议哈希。SCIP数值容差下的最优性证明不等同于有理数精确证明。

## 资源不足、重试和GPU

不设固定SCIP内存或进程RSS配额，limits/memory保留原生无限标记。每0.5 s监测整机可用内存；低于总物理内存25%时，输出RESOURCE_INSUFFICIENT和实际剩余量，仅停止新求解进程。内存/显存/磁盘分配失败也会提示并保留日志。动态保护不能保证操作系统绝不会在两次采样之间耗尽内存。

已提交的最好排程及已有图继续保留；停止后尝试完成最新快照的绘图。尚在验证或写入的最后一次改善可能来不及提交，之前的完整快照不受影响。无可行解时不存在可保留的甘特图。已证不可行显示PROVEN_INFEASIBLE；其他未完成证明显示PROOF_INCOMPLETE或具体失败原因，不记成“最优成功”。

解决资源问题后可以重试：

~~~powershell
& $py -X utf8 -u $large resume --campaign $campaign --retry-failed
~~~

旧solve目录归档到interrupted_attempts；已保存快照不改写，自动载入最近最好赋值作为初始解。重试重新构模，不恢复分支定界树。内存不足时立即重试相同配置通常仍会停止。

若修改方法、GPU或保护比例，应建新campaign。使用同实例最好赋值热启动：

~~~powershell
$best = Get-Content "$campaign/latest_incumbent.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$warm = Join-Path $campaign "$($best.snapshot)/variables.json"
$nextCampaign = 'JMS-version/results/n100_H3_mixed_dual_until_optimal_live_20261111_r2'

& $py -X utf8 -u $large prepare --campaign $nextCampaign --size 100 --recipe mixed --cleaning-interval 3 --dummy-count 8 --method proposed --training-seed 1 --seed 1 --gpu-device 0 --until-optimal --min-available-fraction 0.25 --warm-start $warm
& $py -X utf8 -u $large check --campaign $nextCampaign
if ($LASTEXITCODE -ne 0) { throw '预检失败。' }
& $py -X utf8 -u $large run --campaign $nextCampaign
~~~

仅在latest_incumbent.json已存在时使用热启动命令，16片赋值不能热启动100片实例。

检查时机器为20逻辑处理器、约31.7 GiB RAM和单张RTX 5060 Ti（8151 MiB显存）。此前32片完整表示已有内存停止记录，100片可能在构模完成前触发保护。取消时间上限不能解决构模内存瓶颈。

proposed使用冻结策略在GPU上选割；模型构建、LP和分支定界主要使用CPU/RAM。本次实际GPU载入预检成功。共享同一GPU会争用显存和计算时间，增加GPU占用不能替代MILP所需RAM。入口采用单个SCIP模型；SCIP并发求解需要相应接口和构建支持，不能仅把线程参数调大就视作已启用，见[官方求解接口](https://www.scipopt.org/doc-9.2.3/html/group__PublicSolveMethods.php)。

此任务用于寻找排程及证明最优，资源争用和无时间上限均影响比较口径，不能并入原300 s等时算法对照。

## 本次验证与未完成项

24项自动检查通过，覆盖错误最优声明拒绝、100片50/50完整范围、无时间/节点上限、真实SCIP小模型回调、快照提交及重试、未证最优出图、相同路径改善与最优标注更新，以及严格模式下未完成证明不能计为成功。真实回调测试只解微型测试模型，不是正式排程实验。

已有16片完整赋值另行通过新发布流程检查，177905个变量逐项保存后与原值一致，物理验证通过，并生成实际资源及逐片路线图；此检查不调用优化。

最终严格模式GPU预检记录在results/large_schedule_preflight_20261111_r4，明确model_built=false、solver_started=false。r1/r2/r3是之前的入口预检，原样保留。本次没有构建或求解100片完整模型，100片可行性、完成时间和全局最优仍待实际运行验证。若持续因资源停止，需更大内存或经过等价性证明的可扩展表示；不能截断候选域后把局部最优改称全局最优。
