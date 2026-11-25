# 4片前沿实验的运行与恢复

实验使用连续事件时刻和平方极差目标。纯双曝光实例每个端口供一片，清洁阈值为10，辅助片为8片；原混合实例为两片单曝光、两片双曝光，分别复核清洁阈值3和10。所有结果都在本目录对应的 `JMS-version/results/pareto_four_enriched_20261125/` 下。

## 查看定稿结果

- `pure4_certificate.json` 的 `complete_front` 字段给出纯双曝光实例的完整前沿，包括一个孤立点和三条曲线的公式与开闭端点。
- `pure4_observations.csv` 提供每份排程的路径、摘要、两项目标、驻留均值、极差和原模型约束行数。`sweep_summary.json` 列出各配置实际用过的工期上限。
- `original_mixed_long/H3/` 和 `H10/` 保存原混合实例在450、500、650、800秒上限下的原模型求解记录。全局工艺下界的417秒可行见证保存在 `results/pareto_scales_20261125/four_native_H3/417_pinned/` 和对应的 `H10` 目录。

## 前台运行

以下 PowerShell 命令从仓库根目录启动，沿用实验机器的 Python 环境。换机时，将 `$Py` 指向安装项目原版 PySCIPOpt、SCIP 和 OR-Tools 的解释器。全新复现使用单独工作区，其中保留旧实验输入、原模型和既有排程文件。检查已定稿结果时直接读取上述文件即可。

```powershell
$Py = 'G:/conda/python.exe'
$Code = 'JMS-version/experiments/pareto_four_enriched_20261125'
$Out = 'JMS-version/results/pareto_four_enriched_20261125'
function Invoke-Four {
    param(
        [string]$Script,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Options
    )
    & $Py -B -u -X utf8 (Join-Path $Code $Script) @Options
    if ($LASTEXITCODE -ne 0) { throw "$Script exited with code $LASTEXITCODE" }
}
```

按以下依赖顺序运行。实际计算先用 `mixed_ports --stop-after 1` 中断并恢复一格作验证，随后并行运行整体筛选与纯双曝光筛选。下列顺序适用于单个前台终端，`all` 已含 `double_only`。同一计算单元的产品、阈值、求解种子和预算均由脚本指定。

```powershell
Invoke-Four probe.py mixed_ports --stop-after 1
Invoke-Four probe.py all
Invoke-Four long.py tail --budget 4
Invoke-Four long.py orders --budget 4
Invoke-Four historical.py
Invoke-Four orders.py screen --budget 1.3
Invoke-Four orders.py dense --budget 4
Invoke-Four tail.py
Invoke-Four alternate.py
Invoke-Four middle.py
Invoke-Four original_long.py
Invoke-Four short_projection.py
```

`probe.py` 在三种既有混合排程结构和两种纯双曝光结构上扫描工期上限。`long.py` 的4秒、`orders.py` 的1.3或4秒都是单个 CP 模板的探索时限。`alternate.py` 每个辅助片分配模板使用2秒；`short_projection.py` 枚举24种产品分配，同时至多运行两个单工作线程投影，每种最多3秒。全局结论使用最终最优界、不可行证书和原模型回放。

## 恢复粒度与估时

| 阶段 | 中断后重新执行的命令 | 恢复依据 |
|---|---|---|
| `probe.py`、`tail.py`、`middle.py`、`original_long.py` | 原命令及原参数 | 原生求解按“排程结构、工期上限”保存 `cap_*/result.json`。恢复时核对输入签名以及可行排程和赋值摘要；当前未完成的上限从头求解。各结构的 `progress.json` 记录完成数、累计用时和动态预计剩余时间。 |
| `long.py`、`orders.py`、`alternate.py` | 对应阶段的原命令及原预算 | 每个模板优先跳过已经完成的 `result.json`。若只有 `candidate.json` 则沿用已找到的动作时刻完成原模型回放。尚未找到候选或写入终点的中断模板按同一时限重新探索，恢复粒度为模板或候选。 |
| `historical.py` | `Invoke-Four historical.py` | 已归档的 `archive_catalogue.json` 直接复用。目录筛查期间中断会重新枚举，各独立排程已有的 `historical/*/result.json` 可复用。 |
| `short_projection.py` | `Invoke-Four short_projection.py` | 对 `short_projection/*.json` 中已完成的布局核对脚本签名，补算其余布局。`short_projection_progress.json` 记录进度和动态估时。 |

前台进度按当前阶段已完成单元的耗时或脚本内标明的历史参考估计。CP 探索的时限按单次尝试计，求解树不会跨进程恢复。恢复时从中断的步骤开始，并让同一组搜索由一个前台入口负责。

## 在独立复现目录中生成证书与汇总

取得全部排程和投影后，先生成425秒与408秒两份分段证书，再生成包含491秒段和完整前沿的总证书，最后汇总CSV。下面的命令只补缺失的交付文件。

```powershell
if (-not (Test-Path (Join-Path $Out 'middle_certificate.json'))) { Invoke-Four middle_proof.py }
if (-not (Test-Path (Join-Path $Out 'short_certificate.json'))) { Invoke-Four short_proof.py }
if (-not (Test-Path (Join-Path $Out 'pure4_certificate.json'))) { Invoke-Four certify.py }
$RequiredTables = 'pure4_observations.csv', 'pure4_sample_front.csv', 'summary.json', 'sweep_summary.json'
$MissingTables = $RequiredTables | Where-Object { -not (Test-Path (Join-Path $Out $_)) }
if ($MissingTables) { Invoke-Four publish.py }
```
