# 新清洁规则：证据缺口与重跑命令（2026-10-16）

## 当前 B 窗口结束后的执行顺序

这里的“结束”是程序退出并回到 PowerShell 提示符，不是手动关闭窗口。B 正在运行时，不启动下面的新批次，也不修改冻结代码或调度器。

推荐顺序：**B 验收、A 失败复核 → C → D → E → E2 → F → 按证据缺口选择补充实验**。C/D 与 E 在数据上不依赖彼此；这个顺序按论文证据优先级和资源风险安排。E2/F 不读取 E 的结果，但应先根据 E 的资源失败情况判断是否值得继续扩大规模。

| 顺序 | 批次 | 次数 | 本机执行配置 | 可并行范围 |
|---|---|---:|---|---|
| 0 | 验收 B，复核 A | 不启动新求解 | 读取覆盖表和失败日志 | 可以与其他结果的只读检查同时进行 |
| 1 | C：组件消融 | 216 | 新批次 6000MB/进程，最多2进程，GPU槽1 | 不同实例的纯SCIP任务可并行；学习任务可与另一实例的纯SCIP并行；两个学习任务串行 |
| 2 | D：参数扰动 | 96 | 新批次 6000MB/进程，最多2进程 | 不同实例最多2例并行，无学习GPU任务 |
| 3 | E：规模预检 | 36 | 14000MB/进程，1进程 | 本机逐例运行 |
| 4 | E2：完整析因 | 180 | 14000MB/进程，1进程 | 本机逐例运行；先审查 E 的资源失败 |
| 5 | F：OOD | 81 | 14000MB/进程，1进程，GPU槽1 | 本机逐例运行；大模型可能因资源限制失败 |
| 可选 | C 的 root_only 诊断 | 216 | 与 C 同为6000MB/进程、最多2进程、GPU槽1 | 仅在需要解释分离配置影响时运行 |
| 可选 | B 的1800秒证明预算 | 72（种子1） | 14000MB/进程，1进程 | 仅在界重叠且需要进一步认证排序时运行 |

**只开一个运行实验的 PowerShell 窗口，批次依次执行，批次内部由调度器并行。** 不要同时启动 C 和 D，也不要同时启动两个 C：内存预留和 GPU 槽仅在各自调度器内部计数，没有跨批次的全局协调。同一实例的种子/方法也由当前调度器串行化，以保护共用初始解文件。

本机实测约31.72GiB内存、20个逻辑CPU。按当前规则，两个6GB槽加2GiB预留需要约15848MiB可用内存；两个14GB槽需要约34248MiB，已超过整机内存。6GB双并行是资源许可下的上限，不保证一直双开，也尚未证明所有 C/D 实例均能在6GB内完成。降低内存上限改变实验条件：下面 C/D 使用独立的 `_6gb_p2` 目录，所有对照臂预算一致；不能与 A/B 的14GB观测直接合并为同一算法基准。若出现内存失败，保留失败记录，另建统一预算的对照批次，不只给某个方法临时加内存。

### 第0步：B 返回提示符后先验收

```powershell
Set-Location D:\git\git\RDMCT-A3C
Get-Content JMS-version/results/optional_cleaning_20261016_crossover/finished.json
Get-Content JMS-version/results/optional_cleaning_20261016_crossover/summary/coverage.json
Get-Content JMS-version/results/optional_cleaning_20261016_core/finished.json
```

B 的 `expected` 应为216、`complete_observations` 应为216，并检查是否有 `execution_failed` 或 `pending`。有失败先查看对应 `runs/<单元>/failure.json` 和 `logs`，不要直接当作模型不可行。若是已排除的环境问题或手动中断，可用本文 B 续跑命令追加 `--retry-failed`；确定性的验解错误应先诊断，不能靠反复重跑消除。

A 当前已确认：126例中4例最优、108例限时可行、12例超时无 incumbent、2例执行失败；失败单元为 `n4_H3_mixed_dual__s2__fixed` 和 `n4_H10_mixed_dual__s2__fixed`。A 的 fixed 对照证据仍有缺口；C 不包含 fixed，不能替代这两例。新批次可继续，但相关结论保持待验证。原始记录保留，不在此给出未经诊断的盲目重试命令。

### 后续 C–F 通用前台命令（先在当前窗口执行一次）

下面函数只在目录不存在时执行 `prepare`；目录存在时核对冻结预算后续跑，避免重复创建目录。新开 PowerShell 后需重新定义函数。所有求解在当前窗口前台运行，每15秒显示进度；不启动隐藏进程。准备失败就停止，不接着运行。

```powershell
Set-Location D:\git\git\RDMCT-A3C
$ExperimentPython = 'G:\conda\envs\a3cenv\python.exe'
& $ExperimentPython -c "import psutil, pyscipopt, torch; print('Dependencies OK')"
if ($LASTEXITCODE -ne 0) { throw 'Check dependencies in a3cenv before continuing.' }

function Invoke-ValidationBatch {
    param(
        [string]$Suite, [string]$Output, [int]$MemoryMb, [int]$Jobs,
        [string]$CutProfile = 'standard', [int]$TimeLimit = 300,
        [int]$WallLimit = 1800, [int[]]$Seeds = @(1,2,3),
        [switch]$RetryFailed
    )
    $manifest = Join-Path $Output 'campaign.json'
    if (-not (Test-Path -LiteralPath $Output)) {
        & $ExperimentPython JMS-version/joint_model/revalidate.py prepare --suite $Suite --output $Output --time-limit $TimeLimit --seeds $Seeds --training-seed 1 --spbs-budget 20 --cut-profile $CutProfile --memory-mb $MemoryMb --wall-limit $WallLimit
        if ($LASTEXITCODE -ne 0) { throw 'Prepare failed; inspect the error before running.' }
    }
    if (-not (Test-Path -LiteralPath $manifest)) { throw 'Existing directory has no campaign.json; inspect it without deleting results.' }
    $spec = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifest | ConvertFrom-Json
    if ($spec.suite -ne $Suite -or $spec.memory_mb -ne $MemoryMb -or $spec.time_limit -ne $TimeLimit -or $spec.wall_limit -ne $WallLimit -or $spec.cut_profile -ne $CutProfile -or $spec.training_seed -ne 1 -or $spec.spbs_budget -ne 20 -or ($spec.seeds -join ',') -ne ($Seeds -join ',')) {
        throw 'Frozen campaign settings differ. Use a new output directory; do not overwrite.'
    }
    $retryArguments = @()
    if ($RetryFailed) { $retryArguments = @('--retry-failed') }
    & $ExperimentPython JMS-version/tools/experiment_console.py run --campaign $Output --jobs $Jobs --gpu-slots 1 --reserve-mb 2048 @retryArguments
    if ($LASTEXITCODE -ne 0) { throw 'Run stopped; inspect the error before continuing.' }
    $finishedPath = Join-Path $Output 'finished.json'
    if (-not (Test-Path -LiteralPath $finishedPath)) { throw 'No completion record. Inspect progress before continuing.' }
    $report = Get-Content -Raw -Encoding UTF8 -LiteralPath $finishedPath | ConvertFrom-Json
    $report | Format-List
    if (-not $report.all_cells_successful) { throw 'Queue ended with failed or pending cells; review coverage before continuing.' }
}
```

随后逐段执行下方 **C → D → E → E2 → F** 的函数调用。每批结束检查覆盖和资源失败后再进入下一批；`all_cells_successful=true` 仍可能包含超时无解，不等于所有实例均已找到可行解或论文主张已证实。未改变调度参数时重复同一函数调用会跳过已有完整结果；已记录失败仅在显式加 `-RetryFailed` 后重试。不要在续跑时修改 `Jobs`、预留内存或解释器，调度器也会检查这些冻结设置。

## B 批次报错后的续跑（2026-10-16）

`prepare` 仅对新目录执行一次；目录存在时不要重复执行，也不要删除目录。旧串行入口在启动子进程后才导入 `psutil`，因此缺依赖时可能留下仍在写日志的子进程，立即续跑会遇到 WinError 5。模型和原入口属于冻结哈希，本次保持原文件，用前台入口接管。

在当前 `(a3cenv)` 终端执行：

```powershell
python -m pip install psutil
python JMS-version/tools/experiment_console.py run --campaign JMS-version/results/optional_cleaning_20261016_crossover --adopt-stopped --jobs 2 --gpu-slots 1 --reserve-mb 2048
```

前台入口先检查依赖，再启动任务。接管会拒绝尚存的同批次进程，归档旧进度和停止记录，自动跳过完成单元；之后续跑使用相同命令即可。Ctrl+C 会中断当前求解，重试中断单元需加 `--retry-failed`。不要重复运行同一批次。

现有 B 冻结为每例 14000MB。每槽预留其 1.15 倍，加上系统预留；约 32GB 总内存不足以同时保留两个槽，因此 `--jobs 2` 是并发上限，实际只有 1 个。资源不足时等待。需要真正双并行应另建统一较低内存预算的新批次，不修改已有批次。已有首例使用旧执行协议，转换记录保存在 `scheduler_transitions`，不把跨协议耗时默认为同一基准。

以下 B–F 的 `prepare` 只用于尚不存在的目录；运行统一使用前台入口。

## 2026-10-16执行偏好更新：后续前台并行

核心126次任务队列已结束，覆盖情况见本文第0步。历史后台启动器不再作为执行入口。以后使用前台控制台显示实时完成/失败数量、运行单元和剩余时间；在资源允许时并行。

当前 B 任务的只读实时进度（Ctrl+C仅退出查看，不停止实验）：

```powershell
G:\conda\envs\a3cenv\python.exe JMS-version/tools/experiment_console.py watch --campaign JMS-version/results/optional_cleaning_20261016_crossover
```

以实际运行窗口的进度估计为主。当前只读 `watch` 按配置槽数估算 ETA，B 配置2槽但实际只能1槽时会低估剩余时间，不能据此承诺完成时刻；活动调度器保持冻结，待 B 结束后再修正这个显示问题。后续新批次以本文顶部配置表及 C–F 命令为准。

新前台调度器默认拒绝接管已经以串行方式启动的批次；旧监督器报错且相关进程全部退出后，可用 `--adopt-stopped` 显式接管。同一实例的共用初始解构造与使用串行化，不同实例可并行；学习任务默认共享一个GPU槽。并发数、线程、解释器、调度器哈希单独冻结到 `console_scheduler.json`。Ctrl+C会停止由该前台调度器启动的工作进程并保存中断记录；重新启动时用 `--retry-failed`显式重试。多进程竞争会影响墙钟性能，因此相比较的方法必须采用相同调度协议，不能把串行与并行结果混为同一基准。

当前来源：`JMS-version/JMS_Review_CN.tex`；当前规则为阈值前可选清洁、达到H必须清洁，且不能打断完整2×2处理。用户已选择每例300秒、求解器种子1/2/3；后续改为前台显示进度，资源允许时并行。新批次使用新目录，续跑复用原目录，保留历史数据。

## 先明确不能由旧结果推出的结论

放松清洁触发并扩大候选容量后，旧模型的最优解、下界、模式排序、PDI、运行时间、证明最优率和模型规模不能直接移用于新模型。旧的可行排程可以作为迁移候选，但必须重新通过新模型检查。可行域包含关系不保证300秒内的可行解质量改善。

三个求解器种子是同一个实例的重复，不是三个独立制造实例；核心运行是验证阶段，不能直接复用旧论文的显著性或置信区间。冻结旧检查点的结果仅评价迁移，不能声称已在新模型上训练或证明训练泛化能力。

| 论文位置/主张 | 当前证据不足或失效的具体原因 | 对应实验与命令 | 可接受证据；未达到时如何处理 |
|---|---|---|---|
| 式（5）、（19）；提前清洁扩大可行域并改善排程 | 旧触发仅允许H或特定H−1；单元测试仅证明规则正确，不证明目标改善 | 核心 `legacy` 与 `joint`，命令A | 相同候选容量、物理约束、目标和共同初始解；新模型有效上界低于旧触发模型下界才证明严格改善。否则仅报告观察值和界 |
| 贡献1；释放配对、分腔与周期决策的收益 | 既有联合运行主要保留初始结构；更大可行域不等于限时算法找到了更优结构 | 核心 `fixed` 与 `joint`，命令A | 相同起点、300秒，记录结构是否改变；联合上界低于固定结构下界才证明突破该结构，而不是仅改了时刻 |
| 辅助借用身份带来跨腔重叠（532→403秒） | 该历史见证有价值，但不是新规则或联合搜索算法优势的证据 | 核心n4/H10 `partition` 对 `fixed`，命令A | 除辅助身份外保持产品配对、分腔、周期和侧位；同库存，重新验解并比较上下界。两臂起点因结构不同而不同，不能混入同初始解算法排名 |
| §4.2/表 `tab:joint-refinement-cn`；两阶段改善等待和节拍 | 旧数字对应旧可行域；只有等待下降不能证明节拍改善，短链可能根本没有节拍三连点 | 核心300秒 `joint` 对270+30秒 `refined`；细分消融命令C | 重算物理等待、节拍偏差、有效三连点数；比较总预算并检查回片上界。0个三连点时节拍结果记为不适用 |
| §4.3 SPBS可行率/PDI收益 | 原固定布局的48实例/10种子结果不代表新联合模型 | 核心 `cold`/`serial`/`joint`，命令A | 同模型、同种子、同300秒主求解；无初始解、串行初始解、共用SPBS分别比较。离线构造成本单列，不能写成全流程等墙钟预算优势 |
| §4.3 HEM与完整方法、贡献3 | 旧联合实验学习回调为0或1次；原固定布局比较本就没有显著优势 | 核心 `joint`/`hem`/`proposed`，命令A；角色特征/解码/后处理命令C | 三臂采用完全相同的初始变量赋值与SCIP分离设置；记录实际选割次数、开销、PDI和界。未触发选割不得归因为策略；观察均值接近不得声称显著优越 |
| §4.1及 `tab:joint-grid-cn`：清洁阈值下模式选择 | 旧固定布局与旧清洁规则的排序不能迁移；可行上界之间排序不是全局最优排序 | 核心4/8片H3/H10端点，命令A；8/16/24片H3–10全网格，命令B | 匹配总名义工艺时长、来源、库存和预算。某模式UB低于竞争模式LB才能认证优选；界重叠则排序未决 |
| 单源/双源路线对照 | 旧8个排程只是时刻固定后的手型复核，非新模型下多种子优化比较 | 核心n4/H3单源与双源；命令C、D扩展 | 输入产品、配方、库存保持一致，仅改变来源路线。比较为实例条件下结果，不推出双源普遍最优 |
| §4.5、`tab:joint-perturb-cn` 参数可运行性 | 旧5个单元为旧模型、单种子；不能证明鲁棒性或全参数范围可行 | 命令D | 工艺±10%、库存4/6/10、运输±20%，含名义参照；逐单元验解，完整报告失败和无incumbent |
| §4.4 规模、混流及建模尺寸 | 新安全容量J=T，旧变量数、转折点及R²均已失去对应关系 | 命令E及E2 | 重新记录构建时间、变量/约束、资源失败及求解界。E为规模初筛，E2为4×5×3析因；完成后重新拟合，不能沿用旧R²与系数 |
| §4.6 40–64片OOD全部可行 | 旧729次属固定布局；新联合模型可能首先受内存/构建时间限制 | 命令F | 完整候选容量，不暗中缩小max_pairs/max_cycles；资源失败单独报告，不能用构造器可行替代主求解成功 |
| 真实工厂、在线部署或实际吞吐改善 | 本地模拟和MILP重跑无法验证工业来源、设备执行或闭环实时性 | 无可替代现场数据的命令 | 需要设备日志、接口与现场试验；现阶段不应写成已验证事实 |

## 统一执行与验收规则

- 工作目录：`D:\git\git\RDMCT-A3C`。所有命令在PowerShell中执行。
- 入口：`JMS-version/joint_model/revalidate.py`。`prepare`冻结代码、配置及检查点哈希；运行时检查这些哈希。运行中不要修改相关模型、算法或启动器。
- 每例主预算300秒；两阶段为270+30秒。共用初始解的构造、完整变量补全和至多20秒SPBS单列计时；LP导出及模型构建亦不计入300秒。
- 核心使用 `--cut-profile standard`，即三种算法共享SCIP默认分离配置，取消旧入口强制“根节点最多1轮、非根节点0轮”的限制。回调有机会发生但不保证发生。补充 `root_only` 可检验旧配置限制的影响。
- 全部求解使用完整候选容量；A/B及后续E/E2/F主SCIP内存上限14000MB，新C/D并行批次为6000MB。单进程RSS超过其1.15倍时终止并记录资源失败，单元构建/导出/求解总墙钟保护1800秒（证明预算另设3600秒）。保护性终止不是不可行性证明。单个失败不终止同批次余下队列。
- 每个单元保留LP压缩文件、求解日志、第一/二阶段结果、变量赋值、策略调用记录及 `evidence.json`。后者包含原模型检查、独立物理重放和共用初始解哈希。
- 状态明确区分：`optimal`、`feasible_limit`、`no_incumbent_*`、`proven_infeasible`、`execution_failed`和`pending`。无incumbent超时不是不可行。
- `run`自动跳过完整单元；失败单元仅在指定 `--retry-failed` 后重试。中断尝试会保存到 `interrupted_attempts`，不是恢复SCIP搜索树。
- 每单元结束自动更新 `summary/cells.csv`、`paired_comparisons.json` 和 `coverage.json`。`finished.json`表示队列结束；必须再检查 `all_cells_successful`、expected及状态分布，不能仅凭进程结束宣称实验完成。
- 冻结训练种子默认为1，仅求解器种子为1/2/3。若需要训练重复，对同一矩阵分别指定 `--training-seed 1`、2、3并使用不同目录，禁止把两类种子混为一谈。

## A：已授权的核心实验（126次，主预算合计最多10.5小时）

核心四个对照输入：4片/H3/双源、4片/H3/单源、4片/H10/双源、8片/H3/双源，每个输入8种设置×3种子。再补4/8片H3/H10的三模式端点，复用已有混合模式单元；另加4片/H10的辅助身份对照3次。合计42种输入/设置组合×3种子。

本批已结束，不再执行 `prepare` 或历史后台启动命令。2个 fixed 单元执行失败需诊断；12个超时无 incumbent 是有效的限时观测，不应自动替换成更长预算结果。

查看进度和重新汇总：

```powershell
Get-Content JMS-version/results/optional_cleaning_20261016_core/progress.json
Get-Content JMS-version/results/optional_cleaning_20261016_core/summary/coverage.json
python JMS-version/joint_model/revalidate.py summarize --campaign JMS-version/results/optional_cleaning_20261016_core
```

若诊断需要修改冻结代码，应新建修复后的对照批次，保留原哈希与失败记录，不把修复后的结果静默写回历史实验。

## B：模式网格（216次，主预算最多18小时；另行运行）

```powershell
python JMS-version/tools/experiment_console.py run --jobs 2 --gpu-slots 1 --reserve-mb 2048 --campaign JMS-version/results/optional_cleaning_20261016_crossover
```

若界重叠，追加证明预算须建新目录。例如每例1800秒，用于界收紧，不与300秒算法统计混合：

```powershell
Invoke-ValidationBatch -Suite crossover -Output JMS-version/results/optional_cleaning_crossover_proof1800_14gb_p1 -MemoryMb 14000 -Jobs 1 -TimeLimit 1800 -WallLimit 3600 -Seeds 1
```

这仍可能不能认证排序。它是界收紧实验，不是“保证证明”的命令；必要时只针对未决实例另设更长预算。

## C：算法与精修组件消融（216次，主预算最多18小时）

4/8片、H3/H10、单/双源共8个输入，每个9种设置×3种子。除SCIP、HEM与完整方法外，包含冻结feature-only策略、同一完整策略改为贪心解码、同一策略关闭结构后处理，以及只优化等待和二次节拍惩罚。二次版本明确定义为总等待+10×最大等待+25×节拍二阶差绝对值的平方和；它是新注册对照，不冒称与旧固定布局“二次目标”完全同一实现。

```powershell
Invoke-ValidationBatch -Suite ablation -Output JMS-version/results/optional_cleaning_ablation_6gb_p2 -MemoryMb 6000 -Jobs 2
```

对旧分离配置的诊断，独立保存，不同分离配置的结果不能混为同一处理：

```powershell
Invoke-ValidationBatch -Suite ablation -Output JMS-version/results/optional_cleaning_ablation_rootonly_6gb_p2 -MemoryMb 6000 -Jobs 2 -CutProfile root_only
```

若要评价训练种子变化，用不同输出目录重复C并分别设置 `--training-seed 2`、`--training-seed 3`。这些仍是旧固定策略向新模型的迁移评估；新模型重训练需要单独定义训练/验证/测试划分，不能拿测试集调参后报告测试收益。

## D：参数扰动（96次，主预算最多8小时）

```powershell
Invoke-ValidationBatch -Suite sensitivity -Output JMS-version/results/optional_cleaning_sensitivity_6gb_p2 -MemoryMb 6000 -Jobs 2
```

## E：完整容量模型的规模预检与求解（36次，主预算最多3小时）

```powershell
Invoke-ValidationBatch -Suite scale -Output JMS-version/results/optional_cleaning_scale_14gb_p1 -MemoryMb 14000 -Jobs 1
```

## E2：完整4×5×3析因（180次，主预算最多15小时）

产品数8/16/24/32，4×1产品比例0/25/50/75/100%，工艺时长系数0.9/1.0/1.1，共60个制造输入×3个求解器种子。用新结果重新计算均值、模型规模及析因回归；资源失败必须作为缺失机制报告，不能删去后按完整设计宣布显著。

```powershell
Invoke-ValidationBatch -Suite doe -Output JMS-version/results/optional_cleaning_doe_14gb_p1 -MemoryMb 14000 -Jobs 1
```

## F：40/48/64片分布偏移（81次，主预算最多6.75小时）

九个规模/配方输入×SCIP、HEM、完整方法×3种子。这是新模型的三方法迁移评估，不冒称复现旧729次多方法实验。

```powershell
Invoke-ValidationBatch -Suite ood -Output JMS-version/results/optional_cleaning_ood_14gb_p1 -MemoryMb 14000 -Jobs 1
```

E/F的墙钟可能主要耗在建模上；若触发资源保护，保留为新模型当前实现的规模限制，不能缩减候选集后仍称完整联合实验。A队列已结束，B正在运行；C–F按本文顶部顺序前台执行。各节“主预算合计”是单元求解预算之和，不是承诺的实际结束时间；建模、导出、共用初始解和资源等待另计，并行也不保证时间减半。

## 已完成的入口验证（不作为论文性能结论）

新入口7项初次端到端检查及原相关测试合计92项通过；随后增加固定结构、辅助身份和waiting-only分支，入口10项检查全部通过。五种冻结策略及消融配置均成功装载并通过检查点模式核对。完整预检为1片/H3/双源、种子1、10秒主预算，包含SCIP、9+1秒精修、旧触发、HEM、完整方法五个单元，5/5通过原模型检查和独立重放。旧触发单元证明最优，其他4个为限时可行。HEM/完整方法实际选割分别13/14次；这只证明调用链工作，不能推出算法优势。

预检目录：`results/optional_cleaning_20261016_smoke`。核心正式状态以A目录中的覆盖表为准；未完成结果保持待验证。

2026-10-16核心队列已通过后台启动器实际启动，监督进程和首个工作进程均已确认存活；首例 `n4_H3_mixed_dual__s1__joint` 已生成完整容量模型、接受共用初始解并进入SCIP主求解。启动信息保存在核心目录的 `launch.json`。此处仅记录启动事实，不表示126次实验已经完成。
