表4归一化联合目标：权重敏感性补充方案（2026-11-17）

当前仅准备入口与离线核查，未启动实验。Plan不构模、不求解、不创建结果目录；Prepare仅冻结新的清单；只有Run/Resume启动求解。

已核实的现象
目标为 J=A/A0+rho*B/B0，B=总等待+10*最大单项等待+25*节拍偏差。原代码确实使用rho，并未把权重忽略。
现表4的三个实例在rho=0.01、0.1、1下的联合运行均保留共同初始排程。原始27次联合运行中23次符合预算验收，4片混合的4次超预算结果保持排除。
16片纯4x1的原联合运行在根节点首个LP处达到时限；16片纯2x2在预处理阶段达到时限。结果相同不能解释为权重未进入目标函数。

已知可行排程的权重交点
原冻结批次中4片混合的两个非支配目标向量为(541,1694)和(542,约499)，归一化尺度为A0=542、B0=约499。
二者同分时rho*=(542-541)*B0/((1694-499)*A0)，约为0.00077043。
rho<rho*时前者得分更低，rho>rho*时后者得分更低；这只说明已知两个排程的目标排序，不证明它们覆盖真实Pareto前沿，也不保证300秒内能够搜到它们。
原表权重全部高于该交点。补充0.0001、0.0005、0.001，跨过交点；另补10、100，检查更偏重B时的搜索行为。
16片纯4x1的已知两阶段向量(920,1044)优于联合输入(920,1523)；16片纯2x2对应(2537,约21266)与(2537,22496)。A相同而B更低，故任何正rho都偏好两阶段得到的排程，不存在由这两对向量推出的正权重交换阈值。改变权重是否帮助搜索必须由新实验回答。

固定协议
仅三个表4实例D_n4_mixed、D_n16_4x1、E_n16_2x2；不恢复已删除的N=2实例。
使用原finite_budget_20261116_r1的完整初始赋值、后端D/E、配置、求解种子1/2/3、单线程SCIP和冻结归一化尺度；不把已有较好解重新注入初值。
新增5个权重，共3实例×3种子×5权重=45次，每次300秒名义求解预算，总计3.75个名义求解小时，建模与验解另计。
原0.01/0.1/1及两阶段结果直接复用。两阶段依旧为270秒A加30秒固定主要离散结构的B精修。沿用原预算验收规则，实际阶段用时超过名义预算1秒的结果排除配对，但保留所有原始输出。
最多2路CPU工作进程，大实例按照原内存门槛排队；无学习策略、无GPU任务。Run等待已有正式消融、S1补充及其他已识别研究任务的控制器/工作进程退出，不停止或修改它们。等待时长不计入求解预算。
原worker未修改；每次完整模型检查和独立物理验证均沿用原实现。联合目标下界不能当作A的下界。全部权重/种子的胜、平、负与失败均保留。

命令（在PowerShell中执行）
Set-Location -LiteralPath 'D:\git\git\RDMCT-A3C'

仅查看方案，不启动实验：
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Plan

未来决定执行时，先冻结清单，再在可见终端启动：
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Prepare -Weights 0.0001,0.0005,0.001,10,100
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Run

中断续跑（已完成结果保留，中断尝试归档后按原初值和完整预算重算）：
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Stop
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Resume

状态/汇总：
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Status
& '.\JMS-version\experiments\joint_weight_sensitivity_20261117\control.ps1' -Action Report

结果默认独立保存到JMS-version/results/joint_weight_sensitivity_20261117_r1。
summary/paired_with_existing_two_stage.json保存同种子的有效配对数、A/B均值及原始配对；complete=true才是3种子完整均值。所有输入、基准证据和代码哈希冻结。Prepare拒绝覆盖已有结果目录，Run/Resume不能改权重。仍在运行时再次Run/Resume只提示已有控制器，不重复求解。

核查来源
JMS_Review_CN.tex，tab:joint-two-stage-cn。
experiments/finite_budget_20261116/finite_budget.py，configure_objective、worker、budgets。
results/finite_budget_20261116_r1/campaign.json及runs/*__objectives__*/{input,evidence,trace}.json、solver.log。
4片候选(541,1694)：runs/D_n4_mixed__spbs__s2/evidence.json；另一个候选为共同原输入。
revisions/20261117_joint_objective/objective_evidence.json。
