# 全Pjob严格出片规则对应的实验命令

以下命令使用独立实现 `model4_pjob_fifo_20261029`。旧版本不能通过换参数得到新的顺序约束。

本轮只准备实现、验证和命令，未启动实验批次。等当前队列自然结束后，在可见PowerShell中逐组执行。入口继续显示进度、完成/失败数和ETA，冻结源码、配置及结果，并阻止重叠启动。

```powershell
Set-Location 'D:\git\git\RDMCT-A3C'
$r = '.\JMS-version\model4_pjob_fifo_20261029\run_experiments.ps1'
```

## 主要重跑：102次

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite paper -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
```

`paper`合并并去重以下比较，种子均为1、2、3：

- 四种混合配置的冷启动、串行起点与结构化起点。
- 八种单/双源混合配置的直接求解与第二阶段精修。
- 4/8片、H=3/10、三种配方的双源模式对照。
- 4片、H=10双源混合配置的固定结构和辅助身份重新分配对照。

共16配置、34个配置--方法组合、102次运行。无需再重复旧的完整`core`或`ablation`矩阵。直接求解300秒；精修270+30秒；SPBS 20秒；实际停止时间单独记录。

## 资格与编码：6次

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite qualification -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
```

两种8片混合单/双源配置，每种配方在同一LP中含“仅CH2、仅CH3、两腔均可”三类，共六个Pjob，编号为1--6及26--27。输入保存在新实现的`examples/`内；使用完整精修方法，每配置三个种子。

## 有效节拍消融：48次

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite rhythm -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
```

8片纯2×2、单/双源、H=5/10，比较直接求解、完整线性精修、仅等待精修和二次节拍目标。四种串行参考都已通过顺序与物理检查，并各有两个有效节拍中心。各方法第一阶段仍独立求解；审计中`controlled_comparison=true`的配对才能作为相同起点上的节拍项因果比较。

以上主要实验合计156次。

## 保留学习选割比较时再运行：72次

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite paper_cuts -Jobs 2 -MemoryMB 6000 -ProcessMemoryMB 7000
```

八种混合配置，仅比较默认SCIP、HEM与完整组件，每种三个种子。默认组在本批次内重新使用同一冻结参考，以维持配对条件；不与另一个批次中不同初始赋值的运行直接排名。含本项总计228次。不要求再做全部选割变体、训练规模、DOE或OOD矩阵。

## 保留大规模模式结论时再运行

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite crossover -Jobs 1 -MemoryMB 18944 -ProcessMemoryMB 14336
```

该入口为216次，覆盖8/16/24片。当前活动的旧模式扫描没有全Pjob严格顺序约束，不能替代此版本的运行。当前精简稿已撤下这些模式结论，故这项不是本轮正文的必需实验。32片求解扩展同样可选：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite scale32 -Jobs 1 -MemoryMB 18944 -ProcessMemoryMB 14336
```

## 状态与审计

使用新入口启动时打印的实际批次目录：

```powershell
$campaign = 'JMS-version/results/替换为实际pjob_fifo批次目录'
powershell -ExecutionPolicy Bypass -File $r -Action status -Campaign $campaign
powershell -ExecutionPolicy Bypass -File $r -Action audit -Campaign $campaign
```

已有24组符合新顺序的阶段内精修数值和已筛选的构造序列可复用。旧求解成功率、固定结构降幅、模式与选割排名不能直接移到新约束下；明细见`revisions/20261029_pjob_index_encoding/REVIEW_CN.md`。
