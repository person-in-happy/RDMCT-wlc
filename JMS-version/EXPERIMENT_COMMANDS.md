# 待补实验命令（2026-11-07）

本清单只列未完成项目，不列已完成实验及其复现命令。下面的求解命令尚未执行。

## 1. 当前未完成：32片的6次实验

| 实例 | 待补种子 | 状态 |
|---|---|---|
| 32片、H=3、纯2×2、双源 | 1、2、3 | 种子1内存保护失败；种子2、3未启动 |
| 32片、H=3、混合配方、双源 | 1、2、3 | 未启动 |

目的：补齐这两个配方在100s非加工腔内驻留、100s机械手承片、10000s时域下的限时求解观测。每次主问题300s，无二阶段精修，完整候选容量不变。

独立准备入口只选择父批次没有result.json的单元，不重跑已完成单元，不修改旧结果和原求解程序。由于资源预算改变，新结果须单独标注，不能与旧预算观测合并宣称统一预算下的模式优势。

### 第一步：检查待补范围，不求解

```powershell
Set-Location D:\git\git\RDMCT-A3C
& G:\conda\envs\a3cenv\python.exe -X utf8 JMS-version/tools/prepare_remaining_scale32.py plan --parent JMS-version/results/review_d_scale32_20261105_r1
```

本次应列出6个待补单元。若有其他实验队列在运行，入口会停止，避免读取变化中的队列。

### 第二步：准备仅含待补单元的新批次

整体复制以下代码。预留2048MiB给系统，SCIP预算取进程RSS预算的80%；要求RSS预算高于原失败上限14592MiB，SCIP预算不低于原11520MiB。预算提高不保证内存足够或一定取得可行解。

```powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$campaign32 = 'JMS-version/results/review_d_scale32_remaining_20261107_r2'
if (Test-Path -LiteralPath $campaign32) { throw 'Campaign exists. Do not prepare over it.' }
$availableMiB = [double](& $py -c "import psutil; print(psutil.virtual_memory().available/1024**2)")
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect available RAM.' }
$rssMiB = [int]([math]::Floor(($availableMiB - 2048) / 256) * 256)
$solverMiB = [int]([math]::Floor(($rssMiB * 0.8) / 256) * 256)
if ($rssMiB -le 14592 -or $solverMiB -lt 11520) { throw 'Insufficient budget increase. Do not repeat the failed protocol.' }
Write-Host "Available=$availableMiB MiB; SCIP=$solverMiB MiB; process=$rssMiB MiB"
& $py -X utf8 -u JMS-version/tools/prepare_remaining_scale32.py prepare --parent JMS-version/results/review_d_scale32_20261105_r1 --campaign $campaign32 --memory-mb $solverMiB --process-memory-mb $rssMiB
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed. Do not run.' }
```

准备成功的最后一条JSON应显示 `remaining: 6`、`solver_started: false`。入口继承原实例、种子、时间预算及热启动，记录排除项和父批次哈希，再冻结新协议。中间标准准备器可能先打印9个模板单元；以最后6个待补单元和下述status为准。准备中途失败不得执行run。

### 第三步：前台运行

```powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$driver = 'JMS-version/model4_pjob_nonprocessing_20261103/paper_defaults.py'
$campaign32 = 'JMS-version/results/review_d_scale32_remaining_20261107_r2'
& $py -X utf8 $driver status --campaign $campaign32
if ($LASTEXITCODE -ne 0) { throw 'Protocol check failed. Do not run.' }
& $py -X utf8 -u $driver run --campaign $campaign32
```

首次status应为 `expected=6, complete=0, failed=0, pending=6`。串行运行，不与其他大模型实验并行。六次主问题预算合计30分钟，建模、导出及验证另计，不是30分钟完成保证。

### 续跑未启动单元

```powershell
Set-Location D:\git\git\RDMCT-A3C
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/model4_pjob_nonprocessing_20261103/paper_defaults.py resume --campaign JMS-version/results/review_d_scale32_remaining_20261107_r2
```

仅在新批次没有失败或半成品目录阻挡时适用。已有result.json的单元会跳过；运行中再次失败则仍会停下，不能直接resume越过。没有SCIP搜索树恢复，不删除失败标记。预算仍不足时，应先优化等价模型内存或换主机。

## 2. 若要求全部消融统一为100s，仍缺的实验

以下为条件性证据缺口；稿件如实区分历史扩展配置与100s默认配置时，不要求为已有历史结论重跑。

| 待补实验 | 配对要求 | 当前状态 |
|---|---|---|
| 100s下Pjob库存/逐片表示 | 相同物理输入、完整候选域、目标、种子及预算 | 尚无当前后端的完整配对入口 |
| 100s下固定结构/联合搜索 | 相同已验证初始赋值和总求解预算 | 尚无当前后端的完整配对入口 |
| 100s下节拍权重消融 | 同一第一阶段赋值，有有效节拍中心，仅改变权重 | 尚缺合适的100s可行输入及配对入口 |

这些项目尚不能给出经过核验的启动命令。旧后端脚本及paper_cuts不能替代上述实验，也不能将旧参数结果改标为100s结果。
