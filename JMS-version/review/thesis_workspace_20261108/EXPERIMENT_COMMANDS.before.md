# 剩余实验命令（2026-11-08，编码对照完成后）

编码对照r2已24/24完成且有效，结论已补入稿件，不再列出重跑命令。旧编码r1失败记录保留。以下只列未完成项目；本次没有启动正式实验。

| 实验 | 已完成 | 剩余 | 目的 |
|---|---:|---:|---|
| D下固定结构/联合搜索 | 1/36 | 35 | 共同输入下比较联合300s、固定300s、固定60s后联合240s |
| D下独立收尾优化 | 0/12 | 12 | 保持产品完工及二阶段目标上界，检验全部占用结束时间能否缩短 |
| D下SPBS及后续流程 | 0/24 | 24 | 比较共同可行输入下有无SPBS，两臂均再精修与收尾 |
| D下有效节拍输入搜索 | 0/9 | 9 | 搜索至少2个有效节拍中心的可行输入 |
| D下节拍权重消融 | 未准备 | 条件性12至36 | 取得合格输入后，共同赋值下比较0/5/25/100权重 |

## 1. 结构对照：续跑原批次

此次是第二个单元启动前的内存准入暂停，complete=1、failed=0、pending=35，并非求解失败。已完成 `n2_H3_4x1_dual__s1__joint` 不重跑。不要再次start，也不需要--retry-failed。

冻结预算为SCIP 15872MiB、进程RSS 19968MiB、系统预留2048MiB，启动门槛22016MiB。报错时21976MiB，差40MiB。等待入口额外留512MiB启动余量，在可用内存达到22528MiB后续跑；每15秒检查，下一单元若再次内存不足则继续等待。

```powershell
Set-Location D:\git\git\RDMCT-A3C
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/wait_gap_resume.py --campaign JMS-version/results/gap_d_structure_20261108_r1
```

可正常关闭不用的应用释放内存。等待入口不改预算、不删结果、不自动重试求解错误；Ctrl+C可退出等待。

## 2. 收尾优化：12次，首次启动

```powershell
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/default_gap_experiments.py start --suite cleanup --campaign JMS-version/results/gap_d_cleanup_20261108_r1 --stage2-limit 60 --wall-limit 1800
```

## 3. SPBS对照：24次，首次启动

```powershell
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/default_gap_experiments.py start --suite spbs --campaign JMS-version/results/gap_d_spbs_20261108_r1 --time-limit 300 --stage2-limit 60 --wall-limit 1800
```

无SPBS臂主问题300s；有SPBS臂60s结构改进加240s主问题；两臂均再60s精修和60s收尾。从已有可行赋值开始，不测量通用构造器成功率。

## 4. 有效节拍输入搜索：9次，首次启动

```powershell
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/default_gap_experiments.py start --suite rhythm_search --campaign JMS-version/results/gap_d_rhythm_search_20261108_r1 --time-limit 600 --wall-limit 1800
```

三个实例为4片纯2×2、6片纯2×2、6片混合，H=10，各三个种子。附加至少两个节拍中心的见证条件，受限搜索的最优或不可行状态不能推广到原始完整问题。当前已有D输入无有效节拍中心，不能直接用于权重消融。

## 5. 节拍权重：搜索全部结束且有合格输入后启动

```powershell
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/default_gap_experiments.py start --suite rhythm --source-campaign JMS-version/results/gap_d_rhythm_search_20261108_r1 --campaign JMS-version/results/gap_d_rhythm_20261108_r1 --stage2-limit 60 --wall-limit 1800
```

每实例按预定规则选最小成功种子的合格输入，三种子、四权重共享赋值，保留全部结果。无合格输入时，入口在任何消融启动前拒绝执行。

## 中断或内存暂停后

只执行需要续跑的一行，不并行启动。首次创建后不要再次start。

```powershell
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/wait_gap_resume.py --campaign JMS-version/results/gap_d_structure_20261108_r1
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/wait_gap_resume.py --campaign JMS-version/results/gap_d_cleanup_20261108_r1
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/wait_gap_resume.py --campaign JMS-version/results/gap_d_spbs_20261108_r1
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/wait_gap_resume.py --campaign JMS-version/results/gap_d_rhythm_search_20261108_r1
& G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/tools/wait_gap_resume.py --campaign JMS-version/results/gap_d_rhythm_20261108_r1
```

等待入口拒绝包含failure.json的失败批次。若Ctrl+C发生在工作单元内，检查原日志；确认为foreground_interrupted时，直接调用原驱动的 `resume --campaign 对应目录`，它会保留中断尝试后重启该单元。未知半成品和真正的求解错误须先诊断。按实验单元恢复，不恢复SCIP搜索树。

查询状态（其他批次替换目录）：

```powershell
& G:\conda\envs\a3cenv\python.exe -X utf8 JMS-version/tools/default_gap_experiments.py status --campaign JMS-version/results/gap_d_structure_20261108_r1
```

## 资源、预算与证据范围

新批次准备时读取可用内存，预留2048MiB，其余向下取256MiB整数倍作为RSS预算；SCIP预算为RSS的80%后再向下取整。协议随后冻结，不随每个单元改变。其他应用占用增加仍可能导致暂停，使用对应等待命令继续。结构批次原预算不重新计算。

每次单线程、串行、前台输出进度。剩余结构对照名义优化预算175分钟，收尾12分钟，SPBS及后续流程168分钟，节拍搜索90分钟，合计445分钟（7小时25分钟）；条件性权重消融最多再36分钟。建模、导出、验证及等待内存另计，提前最优可能缩短时间，不是实际结束时间承诺。

结构、收尾和SPBS使用四个已有可行输入的小实例，并非随机代表全部规模。100s是非加工腔内驻留和机械手承片上限，处理周期沿用论文参数。complete表示执行记录完整，不保证最优或有改善；需查看summary和逐单元evidence.json。

32片内存瓶颈、选割未显示优势、部分100s实例的原构造器违反非加工驻留限制仍未解决；不列未经验证、只会重复旧协议的命令。
