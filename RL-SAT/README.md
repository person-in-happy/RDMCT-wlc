# RL-SAT：不依赖 SCIP 的组合设备调度器

`RL-SAT/` 是原 `RDMCT-A3C` 项目的旁路扩展。它保留原目录和原运行入口，不修改原有 SCIP、A3C、beam search、结果或甘特图代码；新入口只导入本目录中的 `rl_sat` 包。两条求解链可以在同一仓库中并存。

新链路为：

```text
显式设备配置
  → 固定 canonical pair/4x1 批成员，保留晶圆配对对称消除
  → 结构化初始解按工艺周期与清洗负载平衡 CH2/CH3
  → A3C + beam search 为每个 4x1 批或 2x2 单元选择 CH2/CH3
  → OR-Tools CP-SAT 按候选分腔重建清洗 epoch 并精排详细时序
  → 固定 Cmax 后最小化等待与双腔 idle 的平方和
  → 结果 JSON、旧式 solution 映射和三类 SVG 甘特图
```

运行依赖中没有 SCIP、PySCIPOpt，也不需要读取 `.lp`。已有 `.sol` 只是可选的 canonical 一致性检查输入；解析过程不调用 SCIP，也不会从旧解恢复或补齐调度。

## 适用范围与结论边界

当前实现面向项目中的双腔组合设备：`CH2/CH3`、4 片批容量、`4x1` 与 `2x2` 工艺、ATR/AL/LL/VTR 共享资源、PEC 载片和清洗约束。产品晶圆仍按到达顺序形成 canonical pair，4x1 批成员保持固定；当 `tool.allow_dynamic_chamber_assignment=true` 时，初始解、A3C 和 beam 可以把完整4x1批或2x2单元分配到任一腔室，CP-SAT 随候选分配重新计算每腔工艺周期和清洗。设为 `false` 时恢复原固定 canonical 分腔基线。 结构单位按输入片数自动构造，支持纯4x1、纯2x2、任意混合比例、单片尾对、1～3片4x1尾批以及启用/关闭清洁；它不按10+10算例写死。合法输入仍受真实设备容量约束。

必须准确理解求解器给出的界：

- 动态模式结果标记 `certificate_scope=dynamic_chamber_assignment_cp_sat_abstraction`；canonical 消融结果仍标记 `canonical_assignment_cp_sat_abstraction`。
- 不同 beam 候选可以对应不同 CH 分配；每次 CP-SAT 的 bound、状态和 gap 只证明该候选分配下的详细时序子模型。跨候选取最好结果不构成所有分腔组合的全局证明。
- `OPTIMAL` 不代表原 SCIP Petri MIP或未建模细节的全局最优。
- 因而不得把结果中的条件界改写成原模型的全局 MIP gap，也不得声称新模型与原 MIP 已被形式化证明完全等价。

动态模式下 RL/Beam 产生分腔候选，CP-SAT 负责资源互斥、工序前后、清洗和详细时序；canonical 模式仍只产生固定队列的 release hint。目标保持严格两阶段：先最小化 `Cmax`，再约束 `Cmax` 不恶化并最小化释放等待、LLupper、工艺前腔室等待、处理后、LLlower等待及 CH2/CH3 汇总 idle 的平方和。`schedule_stability` 的单位因此是 `s²`。

## 快速开始

以下命令从 `RDMCT-A3C/RL-SAT` 目录执行。

Windows PowerShell：

```powershell
cd D:\git\git\RDMCT-A3C\RL-SAT
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"

python scripts\verify_no_scip.py --config configs\smoke.json
python scripts\train.py --config configs\smoke.json --output-dir results\smoke-train --device cpu
python scripts\solve.py --config configs\smoke.json `
  --checkpoint results\smoke-train\a3c_dispatch.pt `
  --output-dir results\smoke-solve
python -m pytest -q
```

Linux/macOS：

```bash
cd /path/to/RDMCT-A3C/RL-SAT
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'

python scripts/verify_no_scip.py --config configs/smoke.json
python scripts/train.py --config configs/smoke.json --output-dir results/smoke-train --device cpu
python scripts/solve.py --config configs/smoke.json \
  --checkpoint results/smoke-train/a3c_dispatch.pt \
  --output-dir results/smoke-solve
python -m pytest -q
```

无 checkpoint 的确定性基线：

```powershell
python scripts\solve.py --config configs\smoke.json --output-dir results\smoke-no-rl
```

用旧 `.sol` 检查 canonical 结构一致性：

```powershell
python scripts\solve.py --config configs\experiment.json `
  --checkpoint results\train\a3c_dispatch.pt `
  --warm-start-sol ..\_results\example.sol `
  --output-dir results\from-old-sol
```

旧 `.sol` 不是必需输入。解析器只检查取值大于 `0.5` 的 `assign_full_*` 与 `assign_mix_*` 是否与当前 canonical CH/batch-side/position 完全一致；冲突、未知正赋值或没有可检查正赋值会报错。旧文件不改变 `dispatch_order`，缺失记录不会被当作旧解内容恢复或补齐，原 SCIP 连续时刻也不会注入 CP-SAT。

离线重画甘特图：

```powershell
python scripts\render_gantt.py results\smoke-solve\result.json `
  --output-dir results\smoke-solve\gantt-redraw
```

## 主要产物

典型求解目录包含：

```text
result.json                 规范化调度、任务、状态、目标与元数据
legacy_solution.json        面向原甘特图变量命名习惯的兼容映射（配置可关闭）
gantt/
  overview.svg              资源级总览
  resource.svg              物理资源甘特图
  product.svg               产品晶圆工艺甘特图
  manifest.json             图文件与运行摘要
  index.html                可直接在浏览器审查的索引页
```

训练目录包含 `a3c_dispatch.pt`、逐 episode 的 `metrics.jsonl` 和 `training_summary.json`。benchmark 同时输出 `benchmark.json` 与 `benchmark.csv`；不传 checkpoint 时每个 repeat 执行 2 种方法，传 checkpoint 时执行 3 种方法。

## 配置

所有实验参数必须来自可审查的 JSON：

- `configs/smoke.json`：最短链路与持续集成检查；
- `configs/train.json`：标准 A3C 训练；
- `configs/experiment.json`：较宽 beam 与更长 CP-SAT 预算；
- `configs/ablation.json`：保留 `allow_dynamic_chamber_assignment=false` 的固定 canonical 消融基线；`smoke/train/experiment` 显式启用动态分腔。

这里刻意不依赖旧入口的隐式默认值。原 `PetriMIPConfig` dataclass 的工艺默认值为 `full=180`、`mix=180`、`cleaning_interval=5`，而原 CLI 曾使用 `full=80`、`mix=30`、`cleaning_interval=10`。这三项存在默认漂移，复现实验前必须逐项审查 JSON；不要仅写“使用默认参数”。

`time_scale` 将秒转换为 CP-SAT 整数 tick。`require_exact_scaling=true` 时，不能精确表示的时间值会直接报错，避免悄悄舍入改变可行域。

Hybrid 把 `time_limit_seconds` 作为一次 `solve()` 内所有 CP-SAT 调用共享的总预算：先从中预留不超过 `final_polish_seconds` 的 polish 份额，候选筛选每次最多使用 `candidate_time_limit_seconds`，并按实际剩余时间截断或停止；最终 polish 也只能使用总预算的剩余部分。beam、模型推理、结果整理等 Python 开销不包含在该 CP-SAT 共享预算内，所以端到端墙钟时间可略大于它。直接调用 `CPSATScheduler.solve()` 且不覆盖时限时，`time_limit_seconds` 同时是该单次 scheduler 调用的默认预算。

## 隔离保证

最小静态与运行时检查：

```powershell
python scripts\verify_no_scip.py --config configs\smoke.json
rg -n "^\s*(from|import)\s+(pyscipopt|scip_imports|petri_mip_generator)" rl_sat scripts
```

第二条无匹配是预期结果；检查器自身保存的禁止模块字符串不等于 import。`verify_no_scip.py` 会 AST 扫描 `RL-SAT` 下 Python 文件、安装动态 import guard、导入指定的纯 RL 模块，并在提供配置时构建 canonical problem、完整走一遍环境动作；它不执行 CP-SAT。CP-SAT 的运行隔离与可行性由 smoke `solve.py` 和 pytest 另行验收。

## 进一步阅读

- [改进算法说明](doc/改进算法说明.md)：建模边界、状态/动作/奖励、beam、CP-SAT 与正确解释；
- [实验与审查指南](doc/实验与审查指南.md)：完整命令、每步目的、输入、输出和验收标准。
