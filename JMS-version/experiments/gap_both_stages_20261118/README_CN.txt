两阶段分别按最优性间隙停止（2026-11-18）

规则
  第一阶段优化 A=Cmax，达到 -Gaps 指定阈值或证得最优后才进入第二阶段。
  第二阶段优化 B=等待总和+10*最大等待+25*节拍偏差，达到 -SecondaryGap
  指定阈值或证得最优后结束。默认 SecondaryGap=1.0，即 100%。
  两阶段 limits/time 都设为 SCIP 的无限时间参数，不设总时限或墙钟时限。
  保留原固定结构、Cmax 上界、验证、单线程及内存保护。
  内存中断不是达标，需单独保留和报告。

参数含义
  所有间隙参数均使用比例：1=100%，0.5=50%，0.05=5%。
  SCIP 间隙为 abs(UB-LB)/min(abs(UB),abs(LB))。
  两阶段分别使用自己的目标上下界，不能用第一阶段的间隙代替第二阶段。
  第二阶段为固定结构子问题；100% 门槛在正下界下相当于 UB<=2*LB，可能很快满足。
  正目标值配合零下界不会被算作达到 100%；目标为零且已证最优则正常结束。
  第二阶段达到 100% 不等于第二阶段已证最优，更不是完整模型字典序最优。

默认实验与前台命令（项目根目录 PowerShell）
  沿用当前第一阶段阈值 0.5、0.3、0.8，每档三个案例 × 三个种子，共 27 条。
  先在旧实验终端按 Ctrl+C，等其控制器和 worker 结束；本入口不自动停止旧任务。
  旧协议结果保持原样，新协议用新目录重新运行，不修改正在运行的冻结代码。

  $both='.\JMS-version\experiments\gap_both_stages_20261118\control.ps1'
  $out='D:\git\git\RDMCT-A3C\JMS-version\results\gap_both_stages_20261118_r1'
  & $both -Action Plan -Campaign $out -Gaps 0.5,0.3,0.8 -SecondaryGap 1.0
  & $both -Action Prepare -Campaign $out -Gaps 0.5,0.3,0.8 -SecondaryGap 1.0
  & $both -Action Run -Campaign $out -MaxWorkers 2

  Plan 只读；Prepare 冻结协议、输入与代码，不开始求解。Prepare 不覆盖已有目录。
  两个间隙参数仅在 Plan/Prepare 时传入；Run/Resume 读取冻结值。
  修改第二阶段间隙，例如改为 50%，使用新的目录：
  $out50='D:\git\git\RDMCT-A3C\JMS-version\results\gap_both_stages_sg50_20261118_r1'
  & $both -Action Prepare -Campaign $out50 -Gaps 0.5,0.3,0.8 -SecondaryGap 0.5
  & $both -Action Run -Campaign $out50 -MaxWorkers 2

补跑、查询与汇总
  & $both -Action Resume -Campaign $out -MaxWorkers 2
  & $both -Action Resume -Campaign $out -MaxWorkers 1 -RetryFailed
  & $both -Action Status -Campaign $out
  & $both -Action Report -Campaign $out
  Ctrl+C 保留已完成结果及中断尝试；补跑从原输入重启，不续接 SCIP 搜索树。
  新入口检测其他项目实验时等待；最多两条并行，N=16 同时最多一条。
  前台打印完成/失败/剩余数、阶段、上下界、间隙、内存及实际已运行时间。
  未取得完成样本前 ETA 未知；后续基于已完成样本粗估，不能保证达标时间。

结果和时间
  evidence.json 分别记录 primary_relative_gap、secondary_relative_gap、stages，
  以及 primary_solver_seconds、secondary_solver_seconds、solver_seconds、wall_seconds。
  secondary_certificate 保存第二阶段独立的间隙证书；protocol_eligible 仅在两阶段
  证书均通过、排程验证通过且无资源中断时为 true。
  summary/rows.csv 包括两阶段上下界、间隙、停止状态和单条总耗时。
  summary/timing.json 的 controller_wall_seconds 是累计 Run/Resume 会话墙钟时间，
  包含资源等待和重试，不含会话之间的离线间隔。
  all_attempt_process_wall_seconds_sum 包括已记录的失败和中断尝试；并行时它不等于
  批次实际墙钟时间。强制结束可能丢失最后一次刷新之后的计时，计时覆盖另列。
  group_summary 和 paired_gaps 同时报告解质量及时间；配对基准为 -Gaps 的第一档。
  不把旧总计 300 秒或切换后 300/600 秒结果混作本协议结果或等预算比较。

验证（仅小型合成模型，不启动正式实验）
  & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -m unittest discover -s JMS-version/experiments/gap_both_stages_20261118 -p 'test_*.py' -v
