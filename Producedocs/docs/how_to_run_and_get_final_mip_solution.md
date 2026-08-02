# RDMCT-A3C 完整运行与结果复现指南

> 面向第一次接触半导体组合设备调度、MIP、SCIP 或强化学习割选择的读者。
> 本文按当前代码审计更新于 2026-07-31；命令默认在 Windows PowerShell、仓库根目录执行。

## 1. 先选择你的目标

| 目标 | 从哪里开始 | 结果能否用于论文 |
| --- | --- | --- |
| 确认安装成功 | 本文“CPU 最小闭环” | 否 |
| 学会生成、训练、测试和看甘特图 | 本文第 4–8 节 | 只能调试 |
| 做一个公平的四方法消融 | 本文第 12 节 | 完整协议后才可 |
| 得到 C&IE 投稿级完整实验包 | [`cie/README.md`](../../cie/README.md) | 通过全部门槛后可作为证据 |

“投稿级”表示实验设计、原始数据、可行性验证和统计口径可审计，不表示保证录用。论文是否达到 C&IE 要求还取决于创新性、一般性、效应大小和写作。

## 2. 项目在解决什么问题

系统有两种产品工艺：

- `4x1`：同一 PW 对在一个四口腔体内完成相应处理；
- `2x2`：PW 对跨 CH2/CH3 形成混流加工。

模型同时描述产品晶圆、PEC 晶圆、清洗作业和搬运资源，优化最后一片产品晶圆返回 LP 的时刻：

```text
min c_max
throughput_wph = 3600 × completed_product_wafers / c_max
```

当前 LP 主目标只有 `c_max`。如果 runtime 开启词典序稳定化，才会在基本不恶化最优 `c_max` 的前提下做第二阶段排程紧凑化。

### 2.1 初学者术语

| 术语 | 含义 |
| --- | --- |
| LP / MIP | 生成的数学规划实例；文件扩展名为 `.lp` |
| SCIP / PySCIPOpt | MIP 求解器及其 Python 接口 |
| incumbent | 当前已找到的最好可行解；没有 incumbent 就不能画有效排程 |
| optimal | 已证明当前解达到最优 |
| gap | 最好可行解与对偶界之间的相对差距；越小越好 |
| PDI | primal-dual integral，衡量整个求解过程中的 gap 质量；通常越小越好 |
| `c_max` | 全流程 makespan，越小越好 |
| WPH | 每小时完成晶圆数，越大越好 |
| PW pair | 两片产品晶圆组成的搬运/加工对 |
| PEC | 工艺环境控制晶圆；会循环复用并触发 cleaning |
| ATR/VTR | 前端和真空侧搬运机器人 |
| AL/LL | aligner 与 load lock |
| CH2/CH3 | 两个四口工艺腔体 |
| warm start / SPBS | 求解前提供的可行初解；不改变可行域和最优值定义 |
| training seed | 训练网络的随机重复 |
| solver seed | 同一模型上 SCIP 的随机重复 |

设备与逐晶圆约束的详细背景见[问题描述](sf3_ct_4x1_problem_description.md)和[逐晶圆 MIP](per_wafer_path_mip.md)。

## 3. 安装

### 3.1 基本要求

- Python 3.10 或更高；
- SCIP 与 PySCIPOpt；
- NumPy、SciPy、PyTorch 等 `requirements.txt` 中依赖；
- 训练和学习策略推理需要 CUDA；实例生成、SCIP 默认求解和分析可用 CPU。

当前机器已验证的一个快照是 Python 3.13.5、PySCIPOpt 6.1.0、PyTorch 2.11.0+cu130。它不是强制版本组合；正式实验应保存自己的环境。

```powershell
Set-Location <你的路径>\RDMCT-A3C
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果使用 NVIDIA GPU，先按本机驱动安装匹配的 CUDA PyTorch。配置写为 `cuda:0` 而 CUDA 不可用时程序会报错，不会自动回退。

### 3.2 自检

```powershell
python -c "import sys,numpy,torch,pyscipopt,scipy; print(sys.version); print('numpy',numpy.__version__); print('torch',torch.__version__); print('cuda',torch.cuda.is_available()); print('pyscipopt',pyscipopt.__version__); print('scipy',scipy.__version__)"
.\cie\run_cie_single.ps1 -Stage check -LogId cie_check
```

第二条命令还会检查全部 C&IE 脚本能否解析。若只做 CPU 流程，`cuda False` 可以接受；训练前必须为 `True`。

## 4. CPU 最小闭环

### 4.1 先跑维护好的端到端 smoke

```powershell
.\cie\run_cie_single.ps1 -Stage smoke -LogId cie_smoke
```

它执行“小 LP → SCIP → `.sol` → 独立 `checkSol` → 制造指标 → 实例级统计”。验收：

- 命令退出码为 0；
- raw 的 `error`、`solution_write_error` 为空；
- `solutions/` 有 `.sol`；
- `analysis/cie_manufacturing_metrics.json` 的 `invalid_count=0`。

这个结果只证明环境和求解链路正常。

### 4.2 手工生成一个小混流实例

下面显式写出关键物理参数，避免不同入口的默认值漂移：

```powershell
python petri_mip_generator.py    --output_dir generated_instances\structure_smoke    --instance_name quick_fullflow.lp    --process_mode auto    --mode_4x1_wafers 4    --mode_2x2_wafers 4    --num_pm 2    --batch_size 4    --pec_pool_size 8    --full_process_time 80    --mix_boundary_process_time 30    --mix_internal_process_time 30    --cleaning_interval 10    --cleaning_process_time 160    --warm_start_time_limit 30    --allow_missing_warm_start
```

生成器会给文件名追加日期。检查：

```powershell
Get-ChildItem generated_instances\structure_smoke |
    Select-Object Name,Length,LastWriteTime
```

至少应有 `.lp` 和对应 `_model.md`；若 30 秒内构造成功，还会有 `_warmstart.sol` 与 `_warmstart.meta.json`。`--allow_missing_warm_start` 只允许初解失败后保留 LP，并不关闭初解构造；完全关闭应同时使用：

```powershell
--warm_start_time_limit 0 --allow_missing_warm_start
```

## 5. 一轮 CPU 训练 smoke

仓库的 `configs/petri_structure_smoke_config.json` 使用 CPU、1 epoch、1 sample、单次 SCIP 10 秒，只验证训练和 checkpoint 写盘：

```powershell
python parallel_reinforce_algorithm.py    --config_file configs\petri_structure_smoke_config.json    --generate_petri_instance False    --single_instance_file all    --instance_type structure_smoke    --train_type train   --reward_type primaldualintegral     --baseline_type simple    --policy_type with_token    --use_cutsel_percent_policy True    --seed 1    --scip_seed 1
```

检查：

```powershell
Get-ChildItem data\structure23_smoke -Recurse -File |
    Sort-Object LastWriteTime |
    Select-Object -Last 15 FullName,Length
```

应看到 `variant.json`、文本/表格日志和 `params.pkl` 或迭代 checkpoint。该模型只有一个样本和一轮更新，没有科研结论。

## 6. 测试与甘特图 smoke

```powershell
python parallel_reinforce_algorithm.py    --config_file configs\petri_structure_smoke_config.json    --generate_petri_instance False    --single_instance_file all    --instance_type structure_smoke    --train_type test    --reward_type primaldualintegral     --policy_type with_token    --use_cutsel_percent_policy True    --test_time_limit 10    --seed 1    --scip_seed 1
```

程序会打印：

```text
saved final solutions: <实际JSON路径>
saved gantt outputs under: <实际目录>
```

测试分支会自动从 solution JSON 生成甘特图。也可手工执行：

```powershell
python petri_gantt.py `
    --solution_json <上一步打印的JSON路径> `
    --output_dir gantt_smoke `
    --view all
```

`latest` 只适合这类 smoke。正式实验必须冻结并记录明确的 checkpoint 路径与 SHA-256。

## 7. 保存控制台日志

`cie\run_cie_single.ps1` 已将标准输出和错误分别写到 `cie/results/logs/<LogId>/`。一般 Python 命令可用 transcript：

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
Start-Transcript -Path logs\manual_smoke.log
try {
    python petri_mip_generator.py --help
} finally {
    Stop-Transcript
}
```

正式归档同时保存命令、退出码、commit、配置和产物，不能只截屏。

## 8. 参数先后关系与默认值漂移

### 8.1 参数在哪个阶段生效

| 阶段 | 入口 | 作用 |
| --- | --- | --- |
| 生成实例 | `petri_mip_generator.py` | 把晶圆数、工艺时间、cleaning 和驻留约束固化进 `.lp` |
| 训练/测试 | `parallel_reinforce_algorithm.py` | 从 JSON 读取求解、网络和训练参数 |
| 一键测试 | `run_petri_a3c_beam.py` | 先重新生成实例，再构造 runtime config 并测试 |
| 消融 | `run_ablation_experiments.py` | 在同一实例、初解和预算下比较四种方法 |
| C&IE | `cie/code/*.py` | 使用冻结 LP、模型和正式协议 |

必须记住：

1. `.lp` 生成后，物理参数已经固定；读取已有 LP 时再传晶圆数或加工时间不会修改它。
2. JSON 的 `env` 控制训练样本求解；测试时只有代码明确支持的 CLI 参数会覆盖。
3. `run_petri_a3c_beam.py` 会重新生成实例，不适合复用冻结论文实例。
4. 正式运行不要使用 `latest`，也不要只写“采用默认参数”。

### 8.2 不同入口的时间默认值不同

所有时间单位均为秒。

| 参数 | 直接生成器 CLI | parallel 自动生成/一键测试/消融 | C&IE nominal |
| --- | ---: | ---: | ---: |
| `full_process_time` | 80 | 180 | 180 |
| `mix_boundary_process_time` | 30 | 180 | 180 |
| `mix_internal_process_time` | 30 | 180 | 180 |
| `cleaning_interval` | 10 | 10 | 5 |
| `cleaning_process_time` | 0 | 0 | 500 |
| 0 对应的实际 cleaning 时长 | 160 | 360 | 不适用 |

`cleaning_process_time=0` 不是零时长 cleaning，而是：

```text
effective_cleaning_process_time = 2 × full_process_time
```

正式实验至少显式记录：三类加工时间、搬运/旋转时间、AL/LL 时间、PEC 数、cleaning interval/time、模块和机器人驻留上限。

### 8.3 当前固定结构

| 参数 | 合法/建议值 | 说明 |
| --- | --- | --- |
| `num_pm` | 2 | 对应 CH2、CH3 |
| `batch_size` | 4 | 当前四口模型固定 |
| `pec_pool_size` | 8 或 10 | 至少 `4*num_pm`、不超过 storage 10、可被 `num_pm` 整除 |
| `atr_capacity` | 2 | 当前物理结构固定；CLI 主要校验 |
| `vtr_capacity` | 4 | 当前路径结构固定；CLI 不会重建机器人 |
| 两个 `mix_*_process_time` | 必须相等 | 不相等会拒绝生成 |

消融入口的默认 `pec_pool_size` 已更新为 8。

### 8.4 产品与工艺模式

| 参数 | 用法 |
| --- | --- |
| `total_wafers` | 0 表示从两种工艺数量或 wafer 配置推导 |
| `mode_4x1_wafers` / `mode_2x2_wafers` | `auto/mixed` 下的两类数量 |
| `process_mode=4x1/2x2` | 全部晶圆使用单一工艺 |
| `process_mode=custom` | 配合完整 `mode_sequence` 或稀疏 `wafer_mode_map` |
| `default_wafer_mode` | 给 map 中未列出的 wafer 指定模式 |

奇数个同模式产品晶圆会形成末尾单产品 PW 对，其余槽位由 PEC 补足。

## 9. `chamber_idle_penalty` 为什么改了没有效果

### 9.1 当前真实语义

生成器接收：

```text
--chamber_idle_penalty
```

训练入口自动生成实例时对应：

```text
--petri_chamber_idle_penalty
```

默认值是 `1e-4`。历史设计希望它给腔体加工组之间的秒级 idle slack 加权，例如相邻 `4x1` 组、`4x1→2x2` 切换、`2x2` cycle→bridge/tail 等。

但当前代码中它是为了兼容旧命令、旧配置和 checkpoint 元数据保留的 **legacy/no-op 字段**：

- 生成 LP 的主目标只有 `min c_max`；
- 当前 `schedule_stability` 表达式不读取它；
- 默认 PDI/solving-time reward 不读取它；
- C&IE benchmark 不读取它。

所以设为 0、`1e-4` 或更大非负值，都不会产生旧文档描述的加权效果。正确配置建议：

- 保留默认值以兼容历史 schema；
- 在实验表中标为 `legacy/no-op`；
- 不把它作为论文敏感性变量；
- 不声称它改善 chamber 连续性。

若要让该权重重新生效，必须先修改目标构造、增加单元测试，并重新生成全部 LP；只改命令行数值无效。

### 9.2 真正有效的词典序稳定化

运行时两阶段逻辑是：

1. 阶段 1 最小化 `c_max`；
2. 阶段 2 固定阶段 1 的 `c_max`（允许数值容差），再改善等待/节拍。

阶段 2只有开关为 true 且时间大于 0 才运行：

```json
{
  "env": {
    "lexicographic_schedule_stability": true,
    "lexicographic_stability_time_limit": 60.0,
    "lexicographic_stability_node_limit": 5000,
    "lexicographic_cmax_tolerance": 0.000001,
    "lexicographic_fix_discrete_decisions": true,
    "lexicographic_free_double_decisions": true
  }
}
```

该 60 秒包含在总 `scip_time_limit` 中，不是额外赠送的预算。当前所有
Petri 配置都显式开启阶段 2、使用 `linear`，并设置非零预算：10 秒
smoke 预留 2 秒、30 秒 C&IE 训练预留 5 秒，一般 45–300 秒配置预留
10 秒，3600 秒正式单实例配置预留 60 秒。C&IE runner 的自动值为
`min(60 s, 10% × 本实例总时限)`。最终仍应以 raw/meta 中记录的
effective runtime config 为准。

### 9.3 要压缩 chamber 组间空闲，用 linear 模式

```json
{
  "env": {
    "lexicographic_schedule_stability": true,
    "schedule_stability_mode": "linear",
    "lexicographic_stability_time_limit": 60.0,
    "schedule_linear_wait_weight": 1.0,
    "schedule_linear_max_wait_weight": 10.0,
    "schedule_cadence_deviation_weight": 25.0,
    "schedule_max_wait_time": 0.0,
    "schedule_wait_cap_mode": "hard"
  }
}
```

线性第二阶段目标可理解为：

```text
wait_weight × sum(selected waits)
+ max_wait_weight × maximum individual wait
+ cadence_weight × sum(cadence deviations)
+ optional soft-cap excess penalty
```

`schedule_linear_wait_weight` 压缩总等待，`schedule_linear_max_wait_weight` 防止少数极长等待，`schedule_cadence_deviation_weight` 改善相邻批次节拍。权重只决定第二阶段内部取舍，不允许无界牺牲主目标。

### 9.4 两种等待硬上限不要混淆

生成 LP 时：

```powershell
--max_schedule_wait_time 200
```

它把逐项等待上限写进 `.lp`，0 表示关闭。parallel 自动生成的对应参数是 `--petri_max_schedule_wait_time`。

加载 LP 后的 runtime 参数是：

```json
{
  "schedule_max_wait_time": 200.0,
  "schedule_wait_cap_mode": "hard"
}
```

- `hard`：增加硬约束；即使第二阶段关闭也可能生效；
- `soft`：在线性第二阶段惩罚超出 target 的部分，并用 `schedule_wait_cap_excess_weight` 加权。

硬上限过小会使模型 infeasible。先查看无上限解的 `schedule_max_wait`，再逐步收紧。正式实验只选择一种来源并记录，避免重复增加约束。

### 9.5 只用于报告的平方权重

以下 runtime 参数只用于计算输出中的 `schedule_wait_penalty`，不改变当前第二阶段目标：

```text
schedule_chamber_idle_square_penalty
schedule_pm_wait_square_penalty
schedule_module_wait_square_penalty
schedule_robot_wait_square_penalty
```

PDI 和 solving-time reward 也不会加入这个诊断 penalty；旧的 `lp_solution_value` 分支例外。

### 9.6 其他兼容字段

| 字段 | 当前行为 | 建议 |
| --- | --- | --- |
| `pm_balance_penalty` | 不进入目标 | 保留默认，标注 no-op |
| `post_process_wait_penalty` | 该权重不进入目标 | 保留默认，标注 no-op |
| `ll_wait_penalty` | 该权重不进入目标 | 保留默认，标注 no-op |
| `chamber_nonprocess_wait_square_penalty` | 系数不进入当前目标 | 保留默认，标注 no-op |
| `num_batches` | 主要校验大于 0；槽位由实际 PW 对推导 | 不作为实验因素 |
| `num_steps` | 当前全流程模型未使用 | 保持 13 |
| `pm_transfer_gap` | 当前约束未读取 | 保持默认 |

“能通过参数校验”不等于“进入优化目标”。

### 9.7 C&IE 的口径

当前 C&IE runner 默认使用 `full`：所有算法共享
`lexicographic_schedule_stability=true`、`schedule_stability_mode=linear`
及相同的总时限、阶段 2 时间和节点预算。阶段 1 仍优化 `c_max`，阶段 2
只允许在 `lexicographic_cmax_tolerance` 内改善等待与 cadence；Generic
MILP 没有相应变量时会明确记录 `skipped_non_petri_model`。

算法优势实验不得关闭这两个因素。其作用由独立的单因素实验说明：

| profile | 阶段 2 | 模式 | 与 `full` 的唯一差异 |
| --- | --- | --- | --- |
| `full` | 开 | `linear` | 参考组 |
| `stage2_off` | 关 | `linear` | 只关闭阶段 2 |
| `linear_off` | 开 | `quadratic` | 只移除 linear 目标 |

三组必须使用同一个 Proposed checkpoint、LP、warm start、training/solver
seed、总时限、内存和停止条件。不能拿 `stage2_off` 与另一个算法比较后把
差异归因于第二阶段。

## 10. Warm start 怎么配

warm start 只提供初始可行 incumbent，不改变可行域或最优解定义，但会影响有限时限内的求解轨迹。

混流实例的优先级通常是：

1. `--warm_start_solution_file` 指定的 `.sol`；
2. 与当前 LP SHA-256 匹配的缓存；
3. 在 `warm_start_time_limit` 内构造；
4. 允许缺失时继续无初解求解。

注意：

- pure `4x1` 不需要 mixed SPBS；
- `.meta.json` 的 `instance_sha256` 必须与 LP 一致；
- 修改 LP 后旧 `.sol` 不能继续使用；
- `allow_missing_warm_start` 不等于关闭构造；
- warm-start 构造时间通常不包含在各方法 SCIP 求解时限内，报告端到端时间时要单独说明。

公平比较必须让所有方法使用同一 `.sol` 或全部不用。不要允许每种方法各自构造不同初解。

## 11. 训练参数、seed 和 checkpoint

### 11.1 当前 reward

CLI 默认和 C&IE 正式训练使用：

```text
reward_type = primaldualintegral
```

| reward | 用途 |
| --- | --- |
| `primaldualintegral` | 当前正式默认，评价整个求解轨迹 |
| `solving_time` | 快速诊断，易受 timeout 和机器负载影响 |
| `lp_solution_value` | 旧实验分支，不建议作为当前默认 |

### 11.2 时间限制

- PDI/solving-time 训练样本的时限来自 JSON `env.scip_time_limit`；
- 训练命令的 `--time_limit` 只在旧 `lp_solution_value` 分支覆盖它；
- 测试时 `--test_time_limit > 0` 优先；
- warm start 使用独立的 `--warm_start_time_limit`；
- 词典序第二阶段预算包含在总 SCIP 时限中。

还要统一 node、stall-node、solution、relative-gap 和 absolute-gap 等停止条件。

### 11.3 两类 seed

| 参数 | 控制对象 |
| --- | --- |
| `--seed` | Python、NumPy、PyTorch/CUDA、策略采样 |
| `--scip_seed` | SCIP 随机化和相关构造过程 |

训练分支现在会先用 CLI seed 覆盖配置 seed。正式训练仍需同时传两个参数，并保存 `variant.json`；独立 checkpoint 不能只靠改目录名伪造。

### 11.4 布尔值和模型选择

部分 parallel CLI 仍用大小写敏感字符串判断，必须写：

```text
--generate_petri_instance True
--use_cutsel_percent_policy True
```

小写 `true` 可能被当作 false。`latest` 按修改时间扫描目录，只用于 smoke；论文使用明确模型文件并保存 hash。

### 11.5 训练/验证/测试隔离

若 `algorithm.evaluate_freq > 0`，训练代码要求 `evaluate_kwargs.test_instance_path` 是存在且非空的独立目录，并拒绝训练/验证路径相同。正式实验还要冻结独立 test，不得根据 test 结果回头选模型或调参数。

根 quick 配置当前实际是 8 epochs、每 epoch 4 samples、2 workers、单样本 SCIP 300 秒且使用 CUDA；它不是“几分钟完成”的 CPU smoke。真正最小训练请使用本文第 5 节的 structure smoke；正式 C&IE 训练请使用 [`cie/README.md`](../../cie/README.md) 的 `train-all`。

## 12. 四方法消融

当前脚本的显示名和内部键是：

| 内部键 | 显示名 | 含义 |
| --- | --- | --- |
| `solver_only` | SCIP Default | 不用学习策略 |
| `a3c_only` | A3C Only | 学习割选择，不做结构重排 |
| `beam_only` | Structure Rerank Only | 结构启发式重排 |
| `a3c_beam` | A3C + Structure Rerank | 学习策略加结构重排 |

`beam_only` 是历史内部键，不应在论文中解释成“只做 beam search”。当前 `a3c_beam_decode_type` 默认也是 `greedy`。

诊断模板：

```powershell
$Checkpoint = (Get-ChildItem data\structure23_smoke -Recurse -File -Include params.pkl,itr_1.pkl |   Sort-Object LastWriteTime | Select-Object -Last 1).FullName
$Instance = (Get-ChildItem generated_instances\structure_smoke -File -Filter *.lp | Sort-Object LastWriteTime | Select-Object -Last 1).Name
$WarmStart = (Get-ChildItem generated_instances\structure_smoke -File -Filter *_warmstart.sol |  Sort-Object LastWriteTime | Select-Object -Last 1).FullName

if (-not (Test-Path -LiteralPath $Checkpoint)) { throw 'checkpoint missing' }
if (-not (Test-Path -LiteralPath $WarmStart)) { throw 'warm start missing' }

python run_ablation_experiments.py    --config_file configs\petri_structure_smoke_config.json    --test_model_path $Checkpoint    --instance_dir generated_instances\structure_smoke     --generate_petri_instance False    --single_instance_file $Instance    --methods solver_only,a3c_only,beam_only,a3c_beam    --stability_ablation_profile full    --output_dir ablation_results\structure_smoke    --device cpu    --time_limit 10    --warm_start_solution_file $WarmStart    --a3c_decode_type greedy    --a3c_beam_decode_type greedy    --a3c_max_candidates 64    --a3c_max_selected_cuts 8    --proposed_max_candidates 64     --proposed_max_selected_cuts 8     --heuristic_max_candidates 64    --heuristic_max_selected_cuts 8     --enforce_fair_ablation True     --seed 1     --scip_seed 1
```

这仍是单实例诊断。论文消融至少要求：

- 冻结多个未见实例；
- 所有方法共用 LP、warm start、solver seed、time/memory 和停止条件；
- A3C-only 与 proposed 使用相同 decode 和候选/选择预算；
- 保留 timeout、错误和无 incumbent；
- 使用多个训练 seeds 与 solver seeds；
- 先按制造实例聚合重复，再做配对统计。

当前根消融默认候选/选择上限是 128/30，不是旧文档中的 256/256。

上述四方法命令只回答“算法组件是否带来优势”，必须保持
`--stability_ablation_profile full`。要回答两个排程因素的作用，使用正式
C&IE 单因素入口：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability `
    -CampaignId cie_stability_600s_mem2048_repro_v1 `
    -Seeds '1,2,3,4,5' -TrainingSeeds '1,2,3,4,5' `
    -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 `
    -LogId cie_stability_600s_mem2048_repro_v1
```

该阶段固定 `methods=proposed`，依次运行 `full`、`stage2_off`、
`linear_off`；以 `proposed[full]` 为 reference，在制造实例内先聚合
training/solver 重复，再做配对检验。若只做诊断，可用
`run_ablation_experiments.py --methods a3c_beam` 分别运行三个 profile，
但三条命令除 profile 与输出目录外必须完全相同。

## 13. 怎样判断结果是否可信

### 13.1 单次求解

按顺序检查：

1. `error` 和 `solution_write_error` 是否为空；
2. 是否有 incumbent；
3. `.sol` 能否重新加载并通过 SCIP `checkSol`；
4. status 是 optimal、timelimit、memlimit 还是其他；
5. gap、PDI、time、nodes；
6. `cmax`、WPH、cycle time、资源利用率和物理可行性。

没有 incumbent 时，gap/目标值和甘特图不能按正常可行排程解释。timelimit 并不等于失败，但必须保留并报告。

### 13.2 不要只看求解时间

- optimal rate：证明最优的比例；
- incumbent rate：至少找到可行解的比例；
- PDI：整个求解过程的质量；
- final gap：到时限时的质量；
- PAR-2 或预注册的 timeout 处理；
- nodes：搜索工作量；
- WPH、cycle time、设备利用率：工业意义。

学习策略 GPU 推理只是 SCIP 回调的一部分，平均 GPU 利用率低是正常现象。

### 13.3 正式统计

solver seed 和 training seed 是同一制造实例上的重复，不可当作独立样本扩大样本量。C&IE 流程会先在实例内平均，再使用两侧配对 Wilcoxon 和 Holm 多重比较校正。

## 14. C&IE 投稿级完整流程

唯一入口是 [`cie/README.md`](../../cie/README.md)。顺序为：

1. 环境清单、check、CPU smoke；
2. 冻结策略训练集和 benchmark LP/hash；
3. 从当前数据训练 HEM、feature-only、Proposed 各 5 seeds；
4. validation-only ACS；
5. core/sensitivity/OOD warm start；
6. Validation、Main、稳定化单因素消融、DOE、SPBS、Sensitivity、OOD；
7. 合并、独立验解、制造指标、实例级统计；
8. 完整性门槛和研究数据归档。

预期 raw 行数：

| campaign | 行数 |
| --- | ---: |
| Validation | 4 |
| Main | 2700 |
| Stability | 1500 |
| DOE | 300 |
| SPBS | 960 |
| Sensitivity | 80 |
| OOD | 729 |

当前仓库中的旧正式结果尚不完整，不能直接填 C&IE 最终性能表。真实状态见 [`cie/products/README.md`](../../cie/products/README.md)。

投稿前按 [C&IE 官方作者指南](https://www.sciencedirect.com/journal/computers-and-industrial-engineering/publish/guide-for-authors) 再核对格式、匿名审稿和研究数据要求。当前官方要求研究数据 deposit/citation/linking；不能共享时解释原因，并在投稿时提交 data statement。

## 15. 常见错误

| 现象/错误 | 原因 | 处理 |
| --- | --- | --- |
| `No module named pyscipopt` | SCIP/PySCIPOpt 未安装或环境未激活 | 激活正确环境；按 PySCIPOpt/SCIP 安装方式重装 |
| `CUDA ... required` | JSON 为 `cuda:0` 但 Torch 无 CUDA | 安装匹配 CUDA Torch，或只运行 CPU smoke 配置 |
| 找不到 LP | 生成目录与 `env.instance_file_path` 不一致 | 统一目录；检查日期后缀后的真实文件名 |
| 找不到 held-out validation | `evaluate_freq>0` 但验证目录不存在/为空 | 生成独立 validation，或仅在 smoke 中关闭 evaluate |
| `pec_pool_size` 校验失败 | 当前只能为 8 或 10 | 使用 8；不要沿用旧默认 40 |
| mixed LP 生成失败 | warm start 在时限内未成功且被要求 | 增大时限；诊断时用 `--allow_missing_warm_start` |
| warm start 被拒绝 | `.sol` 对应旧 LP/hash | 为当前冻结 LP 重新生成 |
| 改 penalty 结果不变 | `chamber_idle_penalty` 等是 no-op | 使用有效的 linear lexicographic 配置或硬上限 |
| 收紧等待后 infeasible | hard cap 小于物理可行下限 | 从无上限诊断值逐步收紧 |
| checkpoint schema/feature dim 不匹配 | 13D/23D 或 policy 配置混用 | 使用与训练 variant 一致的配置和方法 |
| `latest` 选错模型 | 按 mtime 递归选到其他运行 | 正式命令传明确 checkpoint |
| C&IE 找不到 5 组模型 | runner 拒绝旧或种子不一致 checkpoint | 执行 `train-all`；legacy 开关只用于 smoke |
| ACS 被意外改变 | 依赖目录里最新 JSON | 正式 Main/OOD 传 `-AcsWeightsFile` |
| PowerShell 多行命令解析失败 | 使用了 cmd 的 `^` 或漏写续行符 | PowerShell 使用反引号 `` ` ``，且其后不能有空格 |
| 无甘特图 | 没有 incumbent/solution JSON | 先解决求解或初解问题，确认控制台打印 solution 路径 |

## 16. 正式归档检查表

- [ ] 记录 Git commit、未提交改动和环境版本。
- [ ] 保存 OS/CPU/RAM/GPU/CUDA/SCIP 机器清单。
- [ ] 冻结 train/validation/test 与所有 LP SHA-256。
- [ ] 显式记录全部物理参数，不能只写“默认”。
- [ ] checkpoint 的训练来源、三种 seed、feature schema 和 SHA-256 可审计。
- [ ] ACS 只用 validation 调参并冻结明确 JSON/hash。
- [ ] 所有方法共享预算、停止条件和 warm start。
- [ ] timeout、memlimit、错误和无 incumbent 不删除。
- [ ] 每个 incumbent 对应 `.sol`，独立验解 `invalid_count=0`。
- [ ] 统计以制造实例为单位，报告效应量和多重比较校正。
- [ ] 保存 raw CSV/JSON、断点、solution、分析、日志和表图生成代码。
- [ ] 论文声明与实际代码一致，尤其是第二阶段稳定化和消融边界。

如果只想确认“代码能跑”，完成第 4–6 节即可；如果目标是投稿证据，必须继续执行 `cie/README.md` 的完整冻结协议。
