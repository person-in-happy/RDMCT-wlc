# T-ASE 补实验建议与命令

## 判断

官方要求与以往方法进行数值比较，并关注自动化贡献；**没有规定必须新跑某一套实验**。冻结Main已有2700行七方法比较，本版已加入，无需因转刊全部重跑。下面是针对当前证据边界的建议，不是期刊强制清单。

所有命令从项目根目录执行，输出到新的T-ASE-version/results时间戳目录。默认仅预览；带--execute才运行。不修改原始LP、checkpoint、已有结果或活动实验启动器。需要当前项目的Python依赖；含学习策略的敏感性比较需要可用CUDA。

```powershell
Set-Location D:\git\git\RDMCT-A3C
```

## 优先级1：SPBS构造成本（建议投稿前补）

已有51.67%到100%的结果是“已提供预计算初始解以后”的主求解收益。它不支持包含初始化的总耗时改善。补充新建SPBS的成功率、构造wall time、构造加验解wall time；按实例聚合种子后给均值、中位数、95分位数和置信区间。失败样本保留。

预览全部48实例×5种子：

```powershell
python .\T-ASE-version\tools\resumable_experiments.py spbs-cost
```

正式测量：

```powershell
python .\T-ASE-version\tools\resumable_experiments.py spbs-cost --construction-limit 180 --execute
```

每项构造名义上限180s，240项仅构造上限之和约12小时，另有模型创建和验解开销；这是预算加总，不是保证的墙钟完成时间。仅检查一实例一随机种子的技术运行：

```powershell
python .\T-ASE-version\tools\resumable_experiments.py spbs-cost --max-instances 1 --seeds 1 --construction-limit 30 --execute
```

该短运行只检查接口，不能代替正式实验。代码逐项复制原LP，在独立目录构造解并对复制的原模型验证；如果当前生成器不能产生与冻结模型兼容的解，会停止并报错，不能把不兼容解记为有效。输出records.json/csv保存输入hash和实际计时。

**限制：**该命令只补构造成本，不会自动形成“端到端同墙钟预算”的因果比较，也不测量进程启动、策略加载和控制器通信延迟。若继续保持本文的离线定位，报告这些成本并保留限定即可；若要声称在线硬实时或端到端加速，需另行实现统一墙钟截止与可执行回退的比较，不能将本结果伪装成该实验。

## 优先级2：扰动条件下的四方法比较（增强证据，非必做）

原80次OFAT只有单方法可运行性，不能支持跨方法鲁棒性排名。固定8个扰动实例、5个求解种子，比较受控SCIP、固定验证集调参ACS、HEM和完整方法；两个学习方法各用5个冻结训练种子，共480项。每项600s/2048MB、相同SPBS与full精修；名义求解预算加总约80小时，另有加载/验解/分析开销。

```powershell
python .\T-ASE-version\tools\resumable_experiments.py sensitivity
python .\T-ASE-version\tools\resumable_experiments.py sensitivity --device cuda:0 --execute
```

脚本先校验冻结checkpoint哈希，再顺序运行。结束后自动调用现有独立验解及实例级分析。不可把480行塞进旧80行的固定协议审计器；两者是不同实验设计。比较应保留未找到incumbent、超时、失败和所有预设扰动，不以随机种子充当独立制造实例。敏感性结果仍是“扰动参数下重新求解”，不是运行中的随机故障恢复。

如需手工再次后处理，将下列目录替换为实际新目录：

```powershell
$run = 'T-ASE-version/results/sensitivity_实际时间戳'
python .\cie\code\analyze_cie_solutions.py --input_dir "$run/runs" --output_dir "$run/analysis" --validate --fail_on_invalid
python .\cie\code\analyze_cie_submission.py --input_dir "$run/runs" --output_dir "$run/analysis" --stage sensitivity --no_plots
```

## 已有数据可补的规模信息

模型规模表已有脚本。若希望独立重建，命令如下；只读现有LP并写新的统计目录：

```powershell
python .\T-ASE-version\tools\resumable_model_scale.py --manifest .\cie\configs\cie_benchmark_suites.json --output-dir .\T-ASE-version\results\model_scale
```

报告变量数、二元变量数、约束数、文件大小和解析时间。不要把解析耗时直接称为完整求解耗时。

## 没有可直接执行命令的证据缺口

- 配方180秒与90+90秒的薄膜质量等效性，需要真实工艺数据/计量实验；现有调度代码不能生成该证据。
- 实机调度、随机到达、加工波动和故障恢复需要相应执行环境；当前仓库接口不足以给出可信的一行实验命令。
- 若把“选割显著优于最新方法”作为核心贡献，需要先确定并实现可比的新基线；现有HEM对照未显著，增加重复次数不能保证结论改变。

本次只做命令计划检查、参数核对和checkpoint哈希验证，没有运行上述正式新实验。

