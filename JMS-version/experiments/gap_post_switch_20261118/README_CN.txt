达到主目标间隙后，第二阶段独立限时 300 秒（2026-11-18 新协议）

预算规则
  第一阶段默认不设求解时间上限，运行到所选间隙达标或证得最优。
  SCIP 相对间隙为 abs(UB-LB)/min(abs(UB),abs(LB))；无有效上下界不能视为达标。
  达标后，第二阶段重新设置 limits/time=300，不扣减第一阶段用时。
  第二阶段提前证得最优即可结束，不为凑足 300 秒空等。
  总求解时间 = 第一阶段实际 SCIP 时间 + 第二阶段实际 SCIP 时间，不限于 300 秒。
  第二阶段保留原固定结构、Cmax 上界与等待/节拍目标，并重置 limits/gap=0。
  这是主目标有质量证书后的固定结构精修，不声称完整字典序最优。
  原来的 3600 秒单条墙钟保护在本协议中取消；内存保护仍有效。
  若设置可选 -PrimarySeconds，则它只是第一阶段安全上限；超时未达标不进入精修。

默认范围
  5%、1%、10% 三档，依次运行；每档三个原案例 × 种子 1/2/3，共 27 条新流程。
  案例：D_n4_mixed、D_n16_4x1、E_n16_2x2。
  使用原冻结完整热启动、模型、SCIP 参数与单线程设置；不加载学习网络。
  5% 主实验和 1%/10% 敏感性均须按本协议重新运行。
  已完成或在运行的总计 300 秒旧实验保留原目录，不能混作新协议的结果。
  旧结果只保留为旧预算观测，不自动导入本次结果或继续旧 SCIP 搜索树。
  本入口不修改旧控制器、冻结协议、结果或论文，也不启动/停止其他批次。
  新协议总时间不同，禁止与原 300 秒加权目标结果写成等预算比较。

在项目根目录 PowerShell 中运行
  若旧敏感性批次仍在前台运行，先在它的终端按 Ctrl+C。
  等旧控制器及它的 worker 全部结束后，再执行下面命令。
  不要只杀一个子控制器：旧 Suite 外层仍可能继续启动下一档。

  $post='.\JMS-version\experiments\gap_post_switch_20261118\control.ps1'
  & $post -Action Plan
  & $post -Action Prepare -Gaps 0.05,0.01,0.10 -SecondarySeconds 300
  & $post -Action Run -MaxWorkers 2

  默认目录：JMS-version/results/gap_post_switch_20261118_r1。
  Plan 只读；Prepare 冻结清单、环境和源码，不构建或求解模型。
  已 Prepare 时直接 Run/Resume；Prepare 不覆盖已有目录。
  更换目录时，每条命令均传 -Campaign 'D:\git\git\RDMCT-A3C\JMS-version\results\新目录名'。
  若脚本执行策略阻止启动，可用前台命令：
  powershell -NoProfile -ExecutionPolicy Bypass -File .\JMS-version\experiments\gap_post_switch_20261118\control.ps1 -Action Run -MaxWorkers 2

只运行 5% 主实验（9 条）的替代命令
  $main='D:\git\git\RDMCT-A3C\JMS-version\results\gap_post_switch_20261118_main_r1'
  & $post -Action Prepare -Campaign $main -Gaps 0.05 -SecondarySeconds 300
  & $post -Action Run -Campaign $main -MaxWorkers 2
  这是默认 27 条全套的替代选择，不建议两套都运行而重复 5%。

补跑与查询
  & $post -Action Resume -MaxWorkers 2
  & $post -Action Resume -MaxWorkers 1 -RetryFailed
  & $post -Action Status
  & $post -Action Report
  Status 可在另一个终端只读查询。Report 应在控制器结束后执行。
  Ctrl+C 仅结束本控制器及其自有 worker，已完成结果保留。
  Resume 跳过完成条目，补未开始或被中断条目；普通程序错误需 -RetryFailed。
  重试保留 attempts/0001、0002…，从原冻结输入重新求解，不续接搜索树。
  已完成但未达标、超限的观测不为了改善结果而重跑。

时间记录
  runs/<cell>/attempts/<编号>/evidence.json：
    primary_solver_seconds：第一阶段实际 SCIP 时间；
    secondary_solver_seconds：第二阶段实际 SCIP 时间，未启动时为空；
    solver_seconds：两阶段实际 SCIP 时间之和；
    switch_wall_seconds：worker 开始到决定切换的实际墙钟时间，未切换时为空；
    wall_seconds：worker 检查输入、建模、求解、切换和验解等到写证据前的墙钟时间。
  同目录 resources.json 的 wall_seconds：父控制器观察到的完整子进程运行时长，
    包含启动、模块导入与退出；受每秒轮询粒度影响。中断尝试也保存。
  summary/rows.csv：逐条完整指标、两阶段时间、总求解时间、worker 与进程墙钟时间。
  summary/timing.json：
    controller_wall_seconds：累计 Run/Resume 会话实际墙钟时间，含资源等待、重试和并行；
    completed_solver_seconds_sum：已完成观测的两阶段求解时间合计；
    all_attempt_process_wall_seconds_sum：包括失败/中断/重试的已记录子进程时长合计。
  并行任务的时长之和不等于批次墙钟时间；两者分别报告。
  会话记录在 sessions/；恢复前的离线间隔不计入 controller_wall_seconds。
  运行中的会话每次进度刷新更新计时；强制终止可能只保留最后一次刷新值，
    timed_attempts/attempts 标识过程计时覆盖，不把缺失计时当成零。
  summary/group_summary.csv/json：各案例、各阈值的有效数、达标数和指标/时间均值。
  summary/paired_gaps.csv/json：与新协议 5% 的同种子配对，同时给出质量和时间差异。
  不输出旧 300 秒联合目标的等预算配对表。

前台进度和资源
  最多两条并行，各一线程；N=16 同时最多一条，保留原内存预留和保护门槛。
  显示完成/失败/剩余数、阶段、上下界、间隙、内存和实际已运行时间。
  第一阶段不再限时，因此首条完成前 ETA 显示未知；之后仅按已完成样本粗估。
  不保证有限时间内能达到所选间隙；等待资源的时间同样计入批次墙钟时间。
  检测到旧控制器或其他项目实验时等待，不自动终止它们。

验证命令（不运行 27 条正式实验）
  & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -m unittest discover -s JMS-version/experiments/gap_post_switch_20261118 -p 'test_*.py' -v
