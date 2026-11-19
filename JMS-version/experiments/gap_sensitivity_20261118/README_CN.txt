两阶段停止规则的参数扰动：独立扩展，不修改正在运行的 5% 主实验

先明确可检验的问题
  参数变化不保证结果变化。2026-11-18 的只读检查中，已完成的三条 N=4 主流程
  均为 UB=542、LB=116、相对间隙 3.672413793（367.24%），300 秒未切换。
  因此改为 1%、10%、20% 很可能仍不能触发精修，不能承诺“换阈值就有提升”。
  Diagnose 仅解释当前已观察到的界和轨迹，不把推断写成新实验结果。
  若长期无法进入第二阶段，应报告该预算下的适用性限制，而非事后抬高阈值到数百个百分点。

默认最少增量设计
  间隙=1%、5%、10%，总预算均 300 秒；三个原案例 × 三个种子。
  复用原 5% 的 9 条（包括仍在进行/尚待完成的条目），只新增 1%/10% 的 18 条。
  新增名义求解预算合计 90 分钟，另有建模、验证和资源等待时间。
  其他模型、初始完整赋值、随机种子、线程、精修目标和可行域均保持原协议。
  第二阶段仍只在主目标达到指定间隙或证得最优后启动，使用剩余预算。
  Run/Resume 从不启动、停止或修改原 5% 批次，仅读取它来做配对。

建议比较的指标
  每个案例单独报告 3 个种子，不混合 D/E 的不同语义。
  必报覆盖数/有效数、达标数、切换数、真实主目标 UB/LB/gap、第一/第二阶段秒数、
  最终 A=Cmax 与 B=总等待+10*最大等待+25*节拍偏差、各 B 分量和同种子配对差。
  未切换的有效结果必须计入整体均值；未切换的切换时间为空，不能当成 0 秒成功。
  仅已切换样本的平均切换时间另列，并显示分母。失败、预算排除和不完整配对均保留。
  如果各阈值均不切换且最终指标相同，结论是“在当前预算与界强度下未观察到阈值效应”，
  不能据此宣称普遍鲁棒，更不能从小幅墙钟差推断算法优势。

默认准备和运行（项目根目录 PowerShell）
  $sens='.\JMS-version\experiments\gap_sensitivity_20261118\control.ps1'
  & $sens -Action Diagnose
  & $sens -Action Plan
  & $sens -Action Prepare
  & $sens -Action Run -MaxWorkers 2

  默认 Suite：JMS-version/results/gap_sensitivity_20261118_r2。
  r1 是入口检查时的未启动准备记录，已由 r2 替代；原始文件保留，不作为实验结果。
  Prepare 只冻结清单和哈希，不求解；已有目录不覆盖，已准备则直接 Run/Resume。
  仍使用原 gap_two_stage.py 求解器实现，原脚本及已冻结原批次都保持不变。
  参数档位按顺序运行，每档最多两条并行；N=16 同时最多一条。
  保留原内存保护、前台进度、补跑规则。检测到原批次/其他实验运行时等待，不能因此另开多份控制器。
  控制器会对整个 Suite 加系统文件锁，防止重复启动；Ctrl+C 后锁由系统释放。

补跑与汇总
  & $sens -Action Resume -MaxWorkers 2
  & $sens -Action Resume -MaxWorkers 1 -RetryFailed
  & $sens -Action Resume -Family Gap -MaxWorkers 1 -RetryFailed -Cells 'D_n4_mixed__s2__gap_two_stage'
  & $sens -Action Status
  & $sens -Action Report

  已完成但未达标、已完成但超预算不重跑；中断自动补，普通执行错误需 -RetryFailed。
  各次尝试的原始日志保留；不接续旧 SCIP 搜索树，不选择最好的一次结果。
  汇总输出在 Suite/summary/，原批次内的文件不被汇总器修改。
  rows.csv/json：逐种子全部观测与来源哈希。
  group_summary.csv/json：逐案例、逐档位的覆盖情况和均值。
  paired_differences.csv/json：相对 5%/300 秒基准的同种子差值；负的 delta_cmax/delta_secondary 表示较小。
  reference_reachability.json：对原 5% 轨迹的只读可达性诊断。
  未完成行和空值保持为空，不补 0、不生成虚构差异。

可选 A：更宽的阈值范围（须另建 Suite）
  $wide='D:\git\git\RDMCT-A3C\JMS-version\results\gap_sensitivity_wide_20261118_r1'
  & $sens -Action Plan -Suite $wide -Gaps 0,0.01,0.05,0.10,0.20
  & $sens -Action Prepare -Suite $wide -Gaps 0,0.01,0.05,0.10,0.20
  & $sens -Action Run -Suite $wide -MaxWorkers 2

  0% 要求主目标证得最优；共 45 条观测、复用 9 条、新增 36 条。
  这是默认 1/5/10 方案的替代扩展，不建议两套都运行，避免重复 1%/10%。
  20% 只是较宽证书的敏感性档位，不是推荐将主方案精度改为 20%。

可选 B：预算扰动诊断（更适合排查“所有阈值都不触发”）
  固定间隙 5%，总预算 300/600/1200 秒；复用 300 秒，新增 18 条，共 270 分钟名义求解预算。
  $bud='D:\git\git\RDMCT-A3C\JMS-version\results\gap_budget_sensitivity_20261118_r1'
  & $sens -Action Plan -Suite $bud -Gaps 0.05 -Budgets 300,600,1200
  & $sens -Action Prepare -Suite $bud -Gaps 0.05 -Budgets 300,600,1200
  & $sens -Action Run -Suite $bud -MaxWorkers 2
  & $sens -Action Resume -Suite $bud -MaxWorkers 1 -RetryFailed
  & $sens -Action Report -Suite $bud

  这回答“增加计算预算是否改善下界、触发精修及两个目标”，不证明阈值本身更优。
  600/1200 秒不与旧 300 秒加权算法写成等预算胜负；相应旧加权配对在新配置中禁用。
  更长预算也不能保证达标。是否把更长预算用于主比较，需要另行匹配所有比较方法。
  可同时准备两个单因素轴（1/5/10%，300/600/1200 秒），不是全因子：
  & $sens -Action Prepare -Suite 'D:\git\git\RDMCT-A3C\JMS-version\results\gap_combined_20261118_r1' -Gaps 0.01,0.05,0.10 -Budgets 300,600,1200
  这包含五个档位（基准一次），新增 36 条；可用 -Family Gap 或 -Family Budget 分开运行。

其他参数的低增量选择
  既有节拍权重 0/5/25/100 的实验继续作为“给定原始结构下的精修权重敏感性”证据复用，
  不作为 5% 门控流程的新结果。权重变化时应比较原始等待和节拍指标；不要把不同权重
  算出的目标值直接当成同一数值尺度比较，必要时统一用 (1,10,25) 重算评价 B。
  已核验 nondecreasing_review_rhythm_20261103_135933 的 N=16、三个种子原记录及输入哈希：
  权重 0：Cmax 约2537、总等待约1000、最大等待65、节拍偏差792；
  权重 5/25/100：Cmax 约2537、总等待约1016、最大等待65、节拍偏差约784。
  这是权重0与正权重间的等待—节拍权衡；这三个正权重之间未观察到实质差异。
  加工/搬运时间、库存、设备能力等物理输入扰动会改变约束与初始解可行性，需重建、
  重新验解并匹配所有基线；不属于本次最少补实验扩展，不套用旧初始解直接报结果。

验证
  & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -m unittest discover -s JMS-version/experiments/gap_sensitivity_20261118 -p 'test_*.py' -v
  不启动正式求解，检查单因素矩阵、基准只读、预算比较范围、未切换/不合格样本处理。
  SCIP 间隙定义：https://scipopt.org/doc/html/PARAMETERS.php （limits/gap）。
