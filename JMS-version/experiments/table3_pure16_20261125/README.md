# 表3的16片纯配方阈值实验

每个算例使用四个上料端口，每端口四片同配方产品，双源、八片虚拟片、清洁间隔10，工艺时长180/90 s，非加工驻留和机械手驻留上限均为100 s。原连续模型时间域为100000 s。两种配方的求解种子均为1。

## 可复用的数据和正式交接

以旧H10纯配方名称检索到65份包含模型输出字段的文件。早期两份工期较短的归档分别为950和905 s，其驻留上限均为10000 s，采用旧腔室编号和产品释放规则。本次仅提取其配对及周期作为候选。另一份历史H3的920 s纯4×1排程没有实际清洁，重新映射且通过本次完整H10模型后作为可行上界进入共同候选流。所有交接都按当前原模型的最终产品归还时刻和实际得到的下界计算。

同一配方的三个A档共享 SPBS 起点。保留候选流上每一次改善的原生工期及其发现时刻，工期界改善也作为事件。依时间顺序检查 `(UB−LB)/LB`，每档交接首个经原连续模型回填及物理回放验证的排程。标记了交接的档位不会被后来的改进追溯替换。每个B采用该交接时的工期上限、固定结构和当前 Huber 驻留目标。相同种子、B阈值及源排程和赋值的校验和完全一致时，复用固定结构求解记录，见对应B目录中的 `reuse.json`。两种配方均保留可执行排程和原生赋值。

## 工期界

- 纯4×1的初始容量界为824 s。标号产品投影中，逐片保留流转路线和配对、前后腔侧装卸、设备和装载锁约束，放宽虚拟片与清洁搬运。工期830 s以内共24种按起始时刻排列的批次数量和腔室组合。搜索保留全部24种模式。已验证的830 s排程仅提供上限和可行初始解。CP-SAT 最终返回最优松弛值和下界828 s，耗时224.46 s。全模型独立回填的828 s排程与此界相等。中间 bound callback 最后一次写入824，最终界以原始求解器摘要为准。带有其哈希的证书为 `results/table3_pure16_20261125/4x1/warm_dual/830/global_bound.json`。
- 纯2×2的初始容量界为785 s。标号产品路线投影得到并证明805 s，耗时177.37 s。保留其产品动作的部分先后顺序、自由搜索虚拟片动作，在相同工期下得到完整可行解。证书见 `results/table3_pure16_20261125/2x2/projection/result.json`。

## 前台续跑与核验

在项目根目录，用以下命令接管仍在运行的工作进程，或续跑已经交接的B并核验结果。

```powershell
G:/conda/python.exe -B -u -X utf8 JMS-version/experiments/table3_pure16_20261125/follow16.py 4x1
G:/conda/python.exe -B -u -X utf8 JMS-version/experiments/table3_pure16_20261125/follow16.py 2x2
G:/conda/python.exe -B -u -X utf8 JMS-version/experiments/table3_pure16_20261125/verify16.py
```

源阶段可使用同目录 `foreground.py prepare`、`foreground.py project`、`foreground.py native` 和 `timed_campaign.py 2x2` 的种子1入口。完整4×1见证还使用独立活动动作模型，其来源和接收时间均见 `4x1/search/active_order_validation/event_*.json`。全局强界可用 `warm_bound4.py JMS-version/results/table3_pure16_20261125/4x1/search/active_order_validation/schedule_830.json 900` 和 `publish_bound.py` 核对。

每个实例的正式控制器显示已完成格数、当前任务、耗时和剩余时间并更新 `retiming/progress.json`。候选求解不保存求解树，可按累计的搜索时间、已有解和界恢复；B不设时间上限，工作进程退出后从原父项重新建树。首个纯2×2的B曾触及6500 MB内存上限，失败记录保存于 `2x2/10pct/10pct/attempt_scip_6500mb`。正式B使用11500 MB，维持同一固定结构、种子、目标和相对间隙。隔离断点测试记录在 `recovery/sublevel_825.json`。

合并的结果 `results/table3_pure16_20261125/threshold_cells.csv` 含每格两阶段上下界、实测间隙、工期、驻留分量及排程哈希。`validation.json` 记录可执行表格条数、输入哈希和按原连续模型重建的独立赋值数。每次核验从逐片装入、加工、卸载和归还时刻重新计算两项目标。
