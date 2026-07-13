# AAAI-27 冲刺：实验、复现与投稿操作手册

更新日期：2026-07-06  
适用系统：Windows 10/11 + PowerShell  
适用读者：第一次接触 Python、MILP、强化学习或学术投稿的人

---

## GPU execution (read this first)

After installing CUDA-enabled PyTorch, verify GPU access before launching any long experiment:

```powershell
.\aaai\run_aaai.ps1 -Stage check
```

`train-hem`, `train-feature-only`, `train-proposed`, `benchmark`, and `benchmark-all` run learned PyTorch policies on `cuda:0` by default. Select a different device with `-GpuDevice cuda:1` when available. These stages now fail immediately if CUDA cannot be used, so no formal run silently changes from GPU to CPU.

`generate-data`, `quick`, `tune-acs`, SCIP Default, and Adaptive Cut Selection remain CPU-only. SCIP is a CPU MILP solver; CUDA accelerates learned policies, not branch-and-bound or ACS tuning.

正式 benchmark 默认使用 `-WarmStart auto` 加载兼容的 SPBS incumbent。SPBS 消融必须另跑一次 `-WarmStart none`，并保持实例、模型、SCIP seed、时间限制和其他参数完全相同。

Always quote comma-separated PowerShell seed lists:

```powershell
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds "1,2,3" -GpuDevice cuda:0
```

## 先说结论：你需要做什么

这个项目已经准备好了：

- 双源混流旋转腔调度模型；
- SCIP、Adaptive Cut Selection、HEM 和本文方法的统一比较程序；
- 多随机种子统计；
- 跨晶圆规模测试；
- 四类通用 MILP 和 MIPLIB 测试接口；
- AAAI-27 官方 LaTeX 模板论文；
- 自动生成 CSV、JSON 和结果报告的程序。

你接下来的工作不是重新写算法，而是按顺序运行实验，把自动生成的正式结果填回论文。

最短流程如下：

```text
检查环境
  ↓
运行 1 分钟左右的快速演示
  ↓
生成正式数据
  ↓
分别训练 HEM 和本文方法
  ↓
在 validation 上调 ACS 权重和选择 checkpoint
  ↓
冻结模型后运行 test
  ↓
把 summary.csv 的数值填进论文
  ↓
编译 PDF、检查页数、提交
```

所有 AAAI 文件都放在仓库根目录的 `aaai/` 中。运行本手册命令后，新增数据、模型和结果也只会写到 `aaai/`。

---

## 1. 先认识几个词，不懂数学也能继续

### 1.1 MILP 是什么

MILP 是“混合整数线性规划”。在本项目中：

- 0/1 变量决定某片晶圆去哪个腔室、属于哪个批次；
- 连续变量决定取片、移动、加工和回片的时间；
- 约束保证机器人不能同时做两件事、AL 只能放一片、PEC 不能被重复使用；
- 目标是让最后一片产品晶圆尽早回到 LP。

### 1.2 SCIP 是什么

SCIP 是求解 MILP 的软件。它会不断生成合法的 cutting planes，简称 cuts，用来缩小搜索范围。

本项目的学习算法不生成新 cut，只负责从 SCIP 已经生成的合法候选中选择和排序。因此不会改变原问题的可行域。

### 1.3 四个比较方法是什么

| 论文名称 | 程序名称 | 通俗解释 |
| --- | --- | --- |
| SCIP Default | `scip_default` | 完全使用 SCIP 自带策略 |
| ACS-Tuned / Adaptive Cut Selection | `adaptive_cutsel` | 调整 SCIP 对四种 cut 指标的权重 |
| HEM | `hem` | 用 13 个通用特征学习选多少 cut、按什么顺序选 |
| Proposed | `rdmct_a3c` | HEM 骨架 + 10 个通用 MIP 变量角色特征 + 结构去冗余 |

### 1.4 为什么必须分别训练 HEM 和本文方法

HEM 的输入是 13 维；本文方法的输入是 23 维。

- HEM checkpoint 的关键权重形状应为 `[512, 13]`；
- 本文方法 checkpoint 的关键权重形状应为 `[512, 23]`。

不能让 HEM 读取 23 维模型，否则比较不公平。

本文方法的 10 个新增维度不再依赖 `route_*`、`mix_*` 等变量名，而是读取 SCIP 自带的变量类型、目标系数、上下界和 cut 系数。因此任意 `.lp`、`.mps` 或 `.cip` 模型都能使用同一套提取器。完整定义见 `aaai/docs/universal_mip_structure_features.md`。

> **非常重要：** 2026-07-06 以前训练的旧 23D 模型使用了另一套特征含义。虽然权重形状同样是 `[512, 23]`，也不能继续使用。程序现在会检查 `cut_feature_schema` 并拒绝旧模型。HEM 的 13D 模型不受影响。

### 1.5 seed 是什么

seed 是随机种子。训练和 SCIP 求解都会受随机性影响。只跑 seed=1 可能碰巧好或碰巧差，因此论文必须跑多个 seed，并报告平均值和波动。

---

## 2. AAAI 目录里有什么

```text
aaai/
├─ run_aaai.ps1        一站式入口，初学者主要运行它
├─ README.md           最短说明
├─ code/               数据生成、ACS 调参、统一测试代码
├─ configs/            训练配置和数据清单
├─ data/               所有实验实例
│  ├─ petri/           双源混流调度实例
│  ├─ milp/            四类通用 MILP
│  └─ MIPLIB2017/      可选的官方 MIPLIB 实例
├─ models/             HEM 和本文方法的训练输出
├─ results/            快速测试、调参和正式结果
├─ docs/               本手册、修改摘要、自审
└─ products/           官方模板、论文、PDF、checklist、投稿压缩包
```

不要把 AAAI 数据再放回根目录的 `data/`、`MILPdata/` 或 `generated_instances/`。

---

## 3. 第一次运行前需要准备什么

### 3.1 硬件建议

最低可以用 CPU 跑通流程，但正式训练建议：

- CPU：8 核或更多；
- 内存：16 GB 最低，32 GB 更稳；
- GPU：6 GB 显存可以训练小模型，12 GB 以上更方便；
- 磁盘：至少预留 30 GB；
- 正式全部实验可能需要数天。

### 3.2 打开正确的 PowerShell 目录

打开 PowerShell，进入仓库根目录：

```powershell
cd G:\git\RDMCT-A3C
```

确认当前目录：

```powershell
Get-Location
```

输出应以 `RDMCT-A3C` 结尾。

### 3.3 安装 Python 依赖

如果项目以前已经能运行，可以跳过安装，直接做环境检查。

首次安装：

```powershell
python -m pip install -r requirements.txt
python -m pip install numpy torch matplotlib
```

如果使用 NVIDIA GPU，请从 PyTorch 官方网站选择与 CUDA 对应的安装命令。普通 `pip install torch` 可能安装 CPU 版；CPU 版能运行，但训练会慢很多。

---

## 4. 第一步：环境检查

运行：

```powershell
.\aaai\run_aaai.ps1 -Stage check
```

这个命令只检查，不训练，也不修改实验结果。

成功时应看到：

- Python 版本；
- NumPy 版本；
- PyTorch 版本；
- `CUDA available: True` 或 `False`；
- PySCIPOpt 版本；
- `run_aaai27_benchmarks.py --help` 的帮助文字；
- 最后一行 `Environment check completed.`。

### 常见错误

| 错误 | 原因 | 处理方法 |
| --- | --- | --- |
| `python is not recognized` | Python 未安装或未加入 PATH | 安装 Anaconda/Python，并重新打开 PowerShell |
| `No module named pyscipopt` | PySCIPOpt 未安装 | `python -m pip install pyscipopt` |
| `CUDA available: False` | 当前 PyTorch 是 CPU 版或驱动不匹配 | 仍可先跑 quick；正式训练前安装 CUDA 版 PyTorch |
| PowerShell 禁止运行脚本 | execution policy 限制 | 当前窗口运行 `Set-ExecutionPolicy -Scope Process Bypass` |

如果环境检查失败，不要继续正式实验；先修到最后出现绿色完成提示。

---

## 5. 第二步：运行快速演示

运行：

```powershell
.\aaai\run_aaai.ps1 -Stage quick
```

它会自动完成：

1. 在 `aaai/data/quick_demo/` 生成三个很小的双源混流调度实例；
2. 生成四类小型 MILP 测试实例；
3. 用 SCIP Default 和 ACS 各跑一次；
4. 把结果写到 `aaai/results/quick_demo/`。

成功时最后会看到：

```text
Quick demo completed. Open aaai/results/quick_demo.
```

打开最新的 Markdown 报告：

```powershell
Get-ChildItem aaai\results\quick_demo\*.md |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
```

### 重要警告

`quick_demo` 使用独立 manifest、极短时间和极低节点限制，只证明程序链路能运行。它不会进入正式 train/validation/test。

它不能写进论文，不能用来声称本文优于 SCIP，也不能用于选择方法。

---

## 6. 第三步：生成正式实验数据

运行：

```powershell
.\aaai\run_aaai.ps1 -Stage generate-data
```

### 6.1 双源混流数据如何切分

| Split | 晶圆组合 | 用途 |
| --- | --- | --- |
| train | `(4,0)`, `(0,4)`, `(4,4)`, `(8,4)`, `(4,8)` | 学习模型参数 |
| validation | `(8,8)`, `(12,4)`, `(4,12)` | 选择 checkpoint 和调参数 |
| test | `(12,12)`, `(16,8)`, `(8,16)`, `(16,16)` | 最终跨规模评价 |

这三个集合必须分开：

- train 可以反复训练；
- validation 可以反复选模型；
- test 只能在方案冻结后运行，不能看完 test 再调参。

### 6.2 四类通用 MILP

程序会生成（Petri 默认使用 8 个可重用 PEC token，当前设备存储上限为 10）：

- Set Cover；
- Multidimensional Knapsack；
- Capacitated Facility Location；
- Maximum-Weight Independent Set。

每类包含 small、medium、large 三个规模，以及 train、validation、test 三种切分。默认共生成 420 个实例。

### 6.3 如何确认生成成功

```powershell
Get-ChildItem aaai\data\petri -Recurse -File | Measure-Object
Get-ChildItem aaai\data\milp -Recurse -File | Measure-Object
```

第一条应至少看到 12 个 Petri `.lp` 文件及说明文件，第二条应看到 420 个 `.mps` 文件。

---

## 7. 第四步：先训练一个 HEM，确认训练流程

第一次不要立刻跑五个 seed。先用一个 seed 检查：

```powershell
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds 1
```

训练输出会进入：

```text
aaai/models/hem/
```

寻找生成的 checkpoint：

```powershell
Get-ChildItem aaai\models\hem -Recurse -Filter params.pkl
```

如果找到了 `params.pkl`，检查是不是 13 维：

```powershell
$hem = Get-ChildItem aaai\models\hem -Recurse -File -Filter params.pkl |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

$env:HEM_CHECKPOINT = $hem
python -c "import os,torch; d=torch.load(os.environ['HEM_CHECKPOINT'],map_location='cpu',weights_only=False); print(d['pointer_net']['encoder.lstm.weight_ih_l0'].shape)"
```

应输出：

```text
torch.Size([512, 13])
```

如果第二个数字不是 13，不能把它当 HEM 基线。

### 7.1 为什么现在日志不会无限增长

两个正式训练配置已经开启精简文本日志。`debug.log` 主要保留：

- `sampling worker ...`：采样进程、步骤、实例和求解状态；
- `forcedcuts length: ...`：SCIP 强制保留的 cut 数量；
- `len cuts: ...`：本轮候选 cut 数量；
- epoch、保存、恢复、警告和错误信息。

完整训练指标仍保存在同目录的 `progress.csv`，没有被删除。单个 `debug.log` 上限为 8 MB，最多保留 `debug.log.1` 和 `debug.log.2` 两个历史文件，所以每次训练的文本日志最多约 24 MB。

如果训练是在代码修改前已经启动的，旧 Python 进程不会自动获得新设置；需要正常停止后重新运行训练命令。不要直接删除仍在写入的日志文件。

---

## 8. 第五步：训练一个本文方法，确认 23 维模型

```powershell
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds 1
```

输出位置：

```text
aaai/models/proposed/
```

检查维数：

```powershell
$proposed = Get-ChildItem aaai\models\proposed -Recurse -Filter params.pkl |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

python -c "import torch; p=r'$proposed'; d=torch.load(p,map_location='cpu',weights_only=False); print(d['pointer_net']['encoder.lstm.weight_ih_l0'].shape)"
```

应输出：

```text
torch.Size([512, 23])
```

再检查特征版本：

```powershell
python -c "import torch; p=r'$proposed'; d=torch.load(p,map_location='cpu',weights_only=False); print(d.get('cut_feature_schema'))"
```

必须输出：

```text
universal_mip_role23_v2
```

如果输出 `None` 或其他名称，这是旧 23D 模型，必须重新训练。

---

## 9. 第六步：正式多种子训练

单 seed 流程成功后，再分别运行五个训练 seed：

```powershell
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds '2,3'
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds '2,3'
```

公平比较的硬规则：

- HEM 和本文方法使用完全相同的 train 数据；
- 使用相同的 epoch、样本数、SCIP 时间、candidate cap；
- 不能只保留表现最好的训练 seed；
- checkpoint 只能根据 validation 选择；
- 选择完成后再运行 test。

当前训练配置分别是：

- `aaai/configs/aaai27_hem_train.json`；
- `aaai/configs/aaai27_proposed_train.json`。

如果机器较慢，可以先把配置中的 `num_epochs` 从 60 改成 5 检查流程；正式实验统一使用 60 epoch、每轮 8 个训练样本和 30 秒 SCIP 采样上限，并在论文中写明。只有训练预算完全一致的 `itr_60.pkl` 才能比较；旧 feature-only run 使用了每轮 16 个样本和 60 秒 SCIP，不能进入正式消融。

---

## 10. 第七步：在 validation 上调 ACS

运行：

```powershell
.\aaai\run_aaai.ps1 -Stage tune-acs -TimeLimit 60
```

结果位置：

```text
aaai/results/acs_tuning/
```

程序会尝试多组四权重：

1. directed cutoff distance；
2. efficacy；
3. integer support；
4. objective parallelism。

默认 `grid_step=0.25`，共 35 组，适合先跑。正式复现原论文的细网格可以把 `aaai/code/tune_aaai27_acs.py` 命令中的 step 改为 0.1，共 286 组，耗时会显著增加。

### ACS 名称必须写准确

- 只在 validation 上找到一个全局权重：论文写 `ACS-Tuned`；
- 使用原论文 GCNN 对每个 test 实例预测权重：才写完整 `Adaptive Cut Selection`；
- 不能为每个 test 实例先试完所有权重，再拿最好的结果当基线，这属于 oracle 泄漏。

---

## 11. 第八步：运行正式 benchmark

如果只想测试一对 checkpoint，最简单的命令是：

```powershell
.\aaai\run_aaai.ps1 -Stage benchmark -Seeds "1,2,3" -TimeLimit 600 -GpuDevice cuda:0
```

`benchmark` 会自动寻找：

- `aaai/models/hem/` 中最新的 `params.pkl`；
- `aaai/models/proposed/` 中最新的 `params.pkl`。

如果要指定模型：

```powershell
.\aaai\run_aaai.ps1 `
  -Stage benchmark `
  -Seeds "1,2,3,4,5,6,7,8,9,10" `
  -TimeLimit 600 `
  -GpuDevice cuda:0 `
  -HemModel '完整的HEM params.pkl路径' `
  -ProposedModel '完整的本文方法 params.pkl路径'
```

### 投稿应使用多训练 seed 汇总

完成 5 个 HEM 和 5 个 Proposed 训练 seed 后，运行：

```powershell
.\aaai\run_aaai.ps1 -Stage benchmark-all -Seeds "1,2,3,4,5,6" -TimeLimit 600 -GpuDevice cuda:0
```

`benchmark-all` 会：

1. 从 checkpoint 路径中的 `--s-<数字>` 识别训练 seed；
2. 只配对 HEM 和 Proposed 都存在的训练 seed；
3. 对每对模型运行相同的 SCIP seeds；
4. 对重复运行的 SCIP/ACS 基线去重；
5. 保留每个学习模型的 `training_seed`；
6. 自动合并 raw CSV、summary CSV 和 Markdown。

投稿填表优先使用：

```text
aaai/results/final_benchmark/combined/
```

单 checkpoint 正式结果进入：

```text
aaai/results/final_benchmark/
```

每次运行或合并会生成：

| 文件 | 用途 |
| --- | --- |
| `*_raw.csv` | 每个实例、每个 seed 的原始结果，是最终证据 |
| `*_summary.csv` | 自动计算的均值、标准差、加速比等 |
| `*.json` | 完整配置、模型路径和所有结果 |
| `*.md` | 人类可读报告 |

不要手工修改 `raw.csv`。如果发现错误，应修程序后重跑，并保留旧结果目录作为审计记录。

---

## 12. 可选：加入 MIPLIB2017

### 12.1 放到哪里

把 `.mps`、`.mps.gz`、`.lp` 或 `.cip` 文件复制到：

```text
aaai/data/MIPLIB2017/
```

不需要修改程序，manifest 已经配置好。

### 12.2 选择实例的原则

建议预先固定 30--50 个实例，并把名单保存到论文补充材料。只能因为以下客观原因排除：

- SCIP 不能读取；
- 需要未安装的外部插件；
- 出现明确数值错误；
- 不是 MILP；
- 超出事先声明的内存限制。

不能因为本文方法表现差而删除实例。

### 12.3 单独运行 MIPLIB

```powershell
python aaai\code\run_aaai27_benchmarks.py `
  --suites miplib2017_transfer `
  --splits test `
  --methods scip_default,adaptive_cutsel,hem,rdmct_a3c `
  --seeds 1,2,3,4,5 `
  --time_limit 600 `
  --hem_model 'HEM params.pkl' `
  --proposed_model '本文方法 params.pkl' `
  --output_dir aaai\results\miplib2017
```

---

## 13. 外行如何读结果

重点看以下指标：

| 指标 | 越大还是越小越好 | 含义 |
| --- | --- | --- |
| `solving_time` | 越小越好 | 实际求解时间 |
| `primal_dual_integral` / PDI | 越小越好 | 整个求解过程中 gap 的累计，适合评价 anytime 表现 |
| `gap` | 越小越好 | 时间结束时离最优证明还有多远 |
| `nodes` | 通常越小越好 | 搜索树节点数，但必须结合时间看 |
| `with_incumbent` | 越高越好 | 是否找到可行解 |
| `optimal` | 越高越好 | 是否证明最优 |
| `mean_speedup_vs_scip` | 大于 1 较好 | 相对 SCIP 的配对加速倍数 |

### 为什么不能只看平均时间

如果某方法只解出简单实例，却在困难实例上没有可行解，它的平均时间可能看起来很短。因此论文必须同时报告：

- mean ± std；
- median；
- shifted geometric mean；
- final gap；
- PDI；
- 可行解率；
- 最优率；
- bootstrap 95% CI；
- Wilcoxon signed-rank test；
- 多 family 时使用 Holm correction。

统一 runner 已生成逐实例配对数据，并自动执行单侧配对 Wilcoxon 检验、Holm 校正和 claim-ready 门槛判断。

---

## 14. 如何把结果填进论文

论文源文件：

```text
aaai/products/rdmct_aaai27.tex
```

搜索：

```text
Frozen-test comparison schema
```

会看到四行：

- SCIP Default；
- ACS-Tuned / ACS；
- HEM (13D)；
- Proposed (23D)。

从 `aaai/results/final_benchmark/*_summary.csv` 填：

| 论文列 | summary.csv 字段 |
| --- | --- |
| PDI | `mean_primal_dual_integral` |
| Time | `shifted_geomean_time`，并在正文补 mean±std |
| Gap | `mean_gap` |
| Opt. | `optimal / runs` |
| Speedup | `mean_speedup_vs_scip` 和 95% CI |

### 填表规则

1. 先冻结 raw CSV；
2. 用同一份 summary 填所有方法；
3. 不允许从不同实验挑最好数字拼表；
4. 不允许只填最好 seed；
5. timeout 不能删除；
6. 所有百分比必须能从 raw CSV 重算；
7. 表格更新后同步修改摘要、Introduction、Conclusion 和 checklist。

---

## 15. AAAI 论文最少需要哪些实验

### 主表：双源混流跨规模

- SCIP Default；
- ACS-Tuned 或完整 ACS；
- HEM 13D；
- Proposed 23D；
- 至少 5 个训练 seed；
- 至少 10 个 SCIP seed；
- small、medium、large；
- PDI、时间、gap、nodes、可行率、最优率。

### 跨类型表

- Set Cover；
- Knapsack；
- Facility Location；
- Independent Set；
- MIPLIB2017（推荐）；
- 分 family 报告，不能只给一个总平均。

### 消融表

至少需要：

| 版本 | 13 通用特征 | 10 通用角色特征 | 高层 cut 数量 | 结构 reranking |
| --- | --- | --- | --- | --- |
| HEM | 是 | 否 | 是 | 否 |
| + Structure | 是 | 是 | 是 | 否 |
| Full | 是 | 是 | 是 | 是 |

当前代码已经严格区分 HEM 13D 和 Full 23D；“23D 但关闭 reranking”的中间消融仍建议作为下一项补充。

---

## 16. 如何增加一个新的实验数据集

假设你得到一批新 `.mps` 文件：

1. 在 `aaai/data/` 下新建文件夹，例如 `aaai/data/new_family/test/`；
2. 把实例放进去；
3. 打开 `aaai/configs/aaai27_benchmark_suites.json`；
4. 在 `suites` 数组中增加：

```json
{
  "name": "new_family_test",
  "family": "new_family",
  "scale": "all",
  "split": "test",
  "root": "../data/new_family/test",
  "glob": "**/*.mps"
}
```

5. 运行：

```powershell
python aaai\code\run_aaai27_benchmarks.py `
  --suites new_family_test `
  --methods scip_default,adaptive_cutsel `
  --seeds 1 `
  --time_limit 10 `
  --output_dir aaai\results\new_family_smoke
```

先跑 SCIP/ACS smoke，确认读取正常，再加入 HEM 和本文模型。

---

## 17. 编译论文

运行：

```powershell
.\aaai\run_aaai.ps1 -Stage paper
```

输出：

```text
aaai/products/rdmct_aaai27.pdf
```

当前模板来自 AAAI-27 官方 Author Kit。投稿前检查：

- US Letter；
- PDF 1.5 或以上；
- 正文最多 7 页；
- 第 8--9 页只能是 references；
- 匿名作者；
- 无页码；
- 无 Type-3 字体；
- 无 overfull box；
- PDF metadata 不泄露作者；
- 源文件与 PDF 内容完全一致。

检查页数：

```powershell
pdfinfo aaai\products\rdmct_aaai27.pdf | Select-String 'Pages|Page size|PDF version'
```

检查字体：

```powershell
pdffonts aaai\products\rdmct_aaai27.pdf
```

`type` 列不能出现 `Type 3`。

---

## 18. Reproducibility Checklist

文件：

- `aaai/products/ReproducibilityChecklist.tex`；
- `aaai/products/rdmct_reproducibility.pdf`。

当前答案是基于“实验尚未完成”的诚实草稿，含 `partial` 和 `no`。正式结果完成后必须逐项更新，尤其是：

- 运行次数；
- 硬件环境；
- 超参数搜索范围；
- 统计显著性；
- 数据和代码公开计划。

不能为了看起来完整而把未完成项目改成 `yes`。

---

## 19. 当前论文能不能立即投稿

格式上可以编译，结构也已完整；科学证据上还不能直接提交。

必须完成：

1. 5 个 HEM 13D 训练 seed；
2. 5 个 Proposed 23D 训练 seed；
3. validation 上 checkpoint 选择；
4. ACS-Tuned 或完整 ACS；
5. Petri test 多 seed；
6. 四类 MILP test；
7. 推荐补 MIPLIB；
8. 结构特征与 reranking 消融；
9. Wilcoxon + Holm；
10. 把结果填入论文并更新所有性能结论。

在完成前，论文中不能写：

- “significantly outperforms”；
- “achieves x% speedup”；
- “generalizes to unseen MILPs”；
- 任何没有 raw CSV 支撑的百分比。

---

## 20. 最后交接清单

让一位没有参与开发的人按下面顺序操作：

```powershell
.\aaai\run_aaai.ps1 -Stage check
.\aaai\run_aaai.ps1 -Stage quick
.\aaai\run_aaai.ps1 -Stage generate-data
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds 1
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds 1
```

如果对方不需要修改代码就能找到：

- 数据；
- 两类 checkpoint；
- raw CSV；
- summary CSV；
- Markdown 报告；
- PDF；

说明复现入口合格。之后再扩到正式多 seed。

遇到问题时，记录以下信息再排查：

```powershell
python --version
python -c "import torch,pyscipopt; print(torch.__version__, torch.cuda.is_available(), pyscipopt.__version__)"
git rev-parse HEAD
Get-ChildItem aaai\models -Recurse -Filter params.pkl
Get-ChildItem aaai\results -Recurse -File
```

保存完整错误信息，不要只截最后一行。
