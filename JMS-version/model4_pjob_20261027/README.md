# 模型4：Pjob批次任务MILP

本目录保留早期 Pjob 求解后端及其冻结复现依赖，原实验入口为本目录 `run_experiments.ps1`。当前稿件采用后续模型，补充实验见[期刊实验命令](../JOURNAL_EXPERIMENT_COMMANDS.md)。历史批次和已有构造性排程保留原归属。

## 实现范围

- `pjobs.py`：按工艺模式、允许腔室建立Pjob，按LP保留库存；输入产品ID仅供覆盖核验和输出解码。
- `joint_pairing_model.py`：`pj_x_Pjob*_LP*_*_*`选择一个任务库存单位，没有按产品身份建立的成员选择变量。
- `model.py`：匿名成员的完整路线、动态来源LP、分腔、加工/清洁、实体辅助片借用、手爪及模块资源、Cmax和第二阶段等待/节拍目标。
- `seed.py`、`reference_completion.py`：按资格生成物理起点、重排可交换标签、补全完整赋值；主搜索释放起点结构。
- `validate.py`与`physical_validate.py`：独立物理重放、Pjob库存/资格和升序解码检查；输出同时检查SCIP原始模型。
- `evidence_supplement.py`、`run_experiments.ps1`：冻结配置、代码、策略和预算，串行准备公共参考，前台调度独立运行，保存失败和审计记录。

同一Pjob可分配多个PW对、周期和腔室。不同Pjob在模式相同且资格有交集时可以配对；不同LP的服务先后不被固定。进入设备后的各匿名物料仍有独立状态和时间。实体辅助片身份不能删除。

设N为产品数、G为非空Pjob-LP组数。先将含产品对与纯辅助对分别编号：含产品对至多N个，首成员可以固定为产品。两类各自前缀激活，标签不决定物理服务顺序。故实际库存选择变量为`2*G*N`，其余候选对上的产品选择固定为零；原始一般写法是`2*G*Pmax`，模型2身份块是`2*N*Pmax`。总变量数、松弛强度和运行速度仍需匹配实验，不能仅凭这一个变量块推断。

## 输入与输出

`Config`仍接受原来的四个LP配方数量；不提供`pjobs`时，自动将同模式产品设为两腔均可并生成Pjob。默认腔室编号为CH2/CH3。旧CH1/CH2实例需要明确输入其腔室编号；仅名称映射不改变物理参数。

显式输入示例：[同一LP内三种资格](examples/pjob_qualification.json)。产品实际编号为1、2、3、26，划分为三个Pjob；第三个任务跨LP1/LP2。任务字段为`id`、`mode`、`chambers`、`wafers`，库存由有序ID表预处理得到。每片产品必须且只能属于一个任务。当前确定性模型没有逐片到达时间或交期；若以后加入这些属性，必须一并纳入分组。

优化结果仍输出`events`、`pairs`、`cycles`、`jobs`和产品回片`cmax`。`jobs.name`是匿名物料句柄，事件通过它关联物料；`jobs.identity`是恢复后的`LPx_Wy`，`wafer_number=25*(LP-1)+槽位`，`pjob`给出批次任务。按每个Pjob-LP组的首次取片时刻升序赋号，不要求整条路线FIFO。

从仓库根目录，在可见PowerShell中运行单例：

```powershell
$tag = Get-Date -Format 'yyyyMMdd_HHmmss'
G:\conda\envs\a3cenv\python.exe -X utf8 -u JMS-version/model4_pjob_20261027/run_experiments.py solve --config JMS-version/model4_pjob_20261027/examples/pjob_qualification.json --output "JMS-version/results/model4_example_$tag" --time-limit 300 --stage2-limit 30 --initialization spbs --initialization-budget 20 --memory-mb 6000
```

这里是300+30秒的单例演示；文稿等预算比较使用统一批次入口，自动分配300或270+30秒，不能将两者混算。

## 验证与证据边界

开发验证覆盖资格拆分、跨Pjob配对、灵活任务分腔、单/双源、两种工艺、原始完整模型中的热启动检查、具体晶圆解码、两阶段求解以及冷启动/串行/固定结构/精修的worker和审计链路。两个限时搜索例还将见证双向送入完整模型2/4检查。

2026-10-28补充了纯4×1、无辅助对和无清洁候选的参考补全回归测试，修复该缩减子模型向SCIP传入Python布尔值的问题；18项开发测试通过。修复前失败记录与实际core预检记录见[本次修复说明](../revisions/20261028_model4_preflight_fix/README.md)。

先前测试错误地要求两个模型均在10秒内证最优，两项因此失败；四个见证的原始约束和物理检查均通过。该次原始记录保存在`../revisions/20261027_model4_backend/timeout_comparisons/`，不会删除或当作等价性反例。修订后的测试检查双向可行映射和有效界一致性，仅在双方确实最优时比较最优值。

小例验收不代表已完成文稿正式实验，不据此宣称模型4更快、所有规模均可解或学习策略优于基线。冻结学习策略的特征按变量类型和约束系数提取；新入口支持重新测量迁移表现，并未声称针对模型4重新训练。

再次运行开发验证（可见前台、单CPU工作进程）：

```powershell
powershell -ExecutionPolicy Bypass -File JMS-version/model4_pjob_20261027/run_validation.ps1
```
