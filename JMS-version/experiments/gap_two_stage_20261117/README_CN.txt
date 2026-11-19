5% 间隙门控两阶段：新增 9 条核心流程，其他证据按原范围复用

实验范围
  D_n4_mixed、D_n16_4x1、E_n16_2x2，各 seed=1/2/3，共 9 条。
  第一目标 A=Cmax。SCIP 全模型求解，原始可行热启动与旧目标对照一致。
  SCIP 相对间隙 abs(UB-LB)/min(abs(UB),abs(LB)) <= 0.05 或证得最优后，
  才进入第二阶段。零/无效下界不能当作达标；300 秒用尽仍未达标则保留第一阶段解。
  第二阶段固定非连续变量（sync_ 除外），约束 Cmax<=第一阶段实际 Cmax+1e-6，
  最小化 B=等待总和+10*最大等待+25*节拍偏差，第二阶段 limits/gap 重置为 0。
  这是“主目标误差有证书时进行固定结构精修”，不声称全局严格词典序最优。

预算与比较
  每条 300 秒 SCIP 名义总求解预算；第二阶段预算=300-第一阶段实际 SCIP 求解秒数。
  保留旧对照的 1 秒软时限资格容差。建模、读取、切换和验证另外计入总墙钟时间。
  全部 9 条最多合计 45 分钟名义求解时间，不是预计现实完成时间。
  默认每条 SCIP 单线程，两条并行，但 N=16 最多一条；所有流程都使用普通 SCIP。
  复用 27 条同案例/同种子/同归一化的旧联合目标记录，其中目前 23 条预算合格。
  4 条原有预算超限记录保留排除标记，不重算或假装完整配对；报告每组实际 paired 数。
  新流程未触发精修也参加结果统计，不仅统计“成功进入第二阶段”的样本。

复用界限
  原 30 组精修对照和原节拍权重实验仅证明其原始给定结构上的精修模块表现。
  不将它们改称“5% 间隙门控流程产生的结果”。其他初始化、割选择、消融实验保留原范围。
  本入口不更新论文数字，不重跑原实验，不训练策略，不加载 torch 或学习策略。
  GPU 不是本入口的加速开关；更换优化器/算法将改变这一组配对比较。

前台运行（项目根目录的 PowerShell）
  $ctl='.\JMS-version\experiments\gap_two_stage_20261117\control.ps1'
  & $ctl -Action Plan
  & $ctl -Action Prepare -RelativeGap 0.05
  & $ctl -Action Run -MaxWorkers 2

  Plan 只读取和验证；Prepare 冻结协议、输入与代码哈希，不构建或求解模型。
  Prepare 不覆盖已有目录。如果已准备过，直接 Run/Resume。
  默认输出：JMS-version/results/gap_two_stage_20261117_g05_r1。
  更换目录：每条命令同时传 -Campaign 'D:\git\git\RDMCT-A3C\JMS-version\results\新的目录名'。
  无需管理员权限；若终端策略阻止脚本，可在前台这样运行：
  powershell -NoProfile -ExecutionPolicy Bypass -File .\JMS-version\experiments\gap_two_stage_20261117\control.ps1 -Action Run -MaxWorkers 2

补跑、重试和查询
  & $ctl -Action Resume -MaxWorkers 2
  & $ctl -Action Resume -MaxWorkers 1 -RetryFailed
  & $ctl -Action Resume -MaxWorkers 1 -RetryFailed -Cells 'D_n4_mixed__s2__gap_two_stage'
  & $ctl -Action Status
  & $ctl -Action Report

  Run 与 Resume 均跳过完成记录，自动补未开始及中断/资源保护终止的任务。
  普通执行错误默认保留；查 console.log/failure.json，解决环境问题后用 -RetryFailed。
  完成但间隙未达标、完成但预算超限的记录不因 -RetryFailed 重跑，避免结果选择。
  每次重试有独立 attempts/0001、0002…，原日志和部分结果全部保留，不删除或移动。
  补跑从最初冻结热启动重新分配 300 秒，不是续接 SCIP 搜索树，不把旧尝试用时混成一条。
  修改冻结模型/脚本/输入后不能直接续跑；需新协议目录，不能悄悄混用不同实现。
  Ctrl+C 停止本控制器及它自己的新 worker；已完成结果保留。再次 Resume 即可补中断条目。
  状态查询可在另一个终端运行；Report 写汇总，需待控制器结束。

资源控制
  默认最多 2 个 worker，各单线程；N=16 串行。机器空闲内存需至少预留 8 GiB。
  启动 N=4 时再预留 4 GiB，N=16 时再预留 12 GiB，并扣除其他新 worker 尚未用到的预留。
  因而单条 N=16 启动前要求至少 20 GiB 可用内存；不足会显示等待，不强行启动。
  每秒抽样进程 RSS；超过 16 GiB、系统可用内存不足 8 GiB或单条墙钟超过 3600 秒，
  仅终止本控制器启动的新 worker，记录为不合格中断，后续可补跑。
  这些是保护阈值，不是操作系统硬内存配额；内存可能在采样间隔短暂超过阈值。
  不改候选集合、模型变量、预处理配置，不导出庞大的 LP，不修改冻结 SCIP 原生内存参数。
  没有单条内存一定更小的承诺；主要减少策略加载和同时驻留的大模型数量。
  -MaxWorkers 1 可降低并发内存，但 N=16 单模型仍需同样内存；不够时应关闭其他大内存应用。
  检测到项目其他实验控制器或 worker 时，启动新 worker 前等待；不停止、不重启旧实验。
  实时打印 completed/failed/running/剩余条目、阶段、上下界、间隙、RSS 和 ETA。
  ETA 初期按名义求解预算估算，之后按已完成条目的实际墙钟时间估算；外部等待无法预估。

输出
  campaign.json / contract.json / frozen_code：冻结协议与代码。
  runs/<cell>/attempts/<编号>/console.log、solver.log、progress.json：单条进度。
  phase1.json / variables_phase1.json / gate.json：阶段一结果与切换判据。
  result.json / variables.json / evidence.json：原完整模型及独立物理验证后的结果。
  resources.json：抽样内存峰值、并行设置和实际墙钟时间。
  summary/coverage.json：9 条覆盖情况、预算合格数、达标数、精修数。
  summary/rows.json：每条结果及失败详情。
  summary/paired_weighted.json：与旧加权目标逐案例逐种子配对，保留不完整配对与排除理由。

验证命令
  & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -m unittest discover -s JMS-version/experiments/gap_two_stage_20261117 -p 'test_*.py' -v
  测试仅有小型合成 SCIP 模型及临时目录，不启动 9 条正式实验。

官方间隙定义与 API
  https://www.scipopt.org/doc/html/PARAMETERS.php （limits/gap、limits/time、timing/clocktype）
  https://pyscipopt.readthedocs.io/en/latest/api/model.html （getGap、getDualbound、freeTransform）
