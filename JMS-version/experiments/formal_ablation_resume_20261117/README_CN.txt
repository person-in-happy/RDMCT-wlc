正式消融的中断与续跑

当前正式批次：JMS-version/results/formal_ablation_20261117_r1
主运行代码与 campaign/contract 保持冻结。本入口是独立控制层，不修改正在运行的求解器或旧批次。

在 PowerShell 中续跑（可从任意目录执行）：
& 'D:\git\git\RDMCT-A3C\JMS-version\experiments\formal_ablation_resume_20261117\resume.ps1'

安全中断当前批次：
& 'D:\git\git\RDMCT-A3C\JMS-version\experiments\formal_ablation_resume_20261117\resume.ps1' -Action Stop

只查看状态：
& 'D:\git\git\RDMCT-A3C\JMS-version\experiments\formal_ablation_resume_20261117\resume.ps1' -Action Status

也可在实验前台按 Ctrl+C 中断。续跑会跳过所有已完成单元，将没有完成证书的中断单元、内存保护或总墙钟保护中断单元的目录、日志和启动记录移动到同一批次 continuations/ 下，完整保留原始输出。中断单元从同一冻结原始输入、同一种子和同一完整预算重新计算；不会把中断前搜到的中间解作为新初值，也不会为了改善结果重跑已完成单元。这是运行单元级续跑，不恢复 SCIP 内部搜索树。

若中断发生在完整验算证书已经写出之后，且结果/赋值哈希仍匹配，则保留这份完成结果，只归档中断标记。其他真正的程序错误、模型验证失败不自动清除，继续列在失败统计中。共享 SPBS 若已完成会继续复用；若其计算中断则连同未运行的依赖关系按原配置恢复。

续跑前检查当前进程、PID 创建时间、冻结代码/输入/检查点哈希与锁。实验仍运行时再次执行续跑命令只提示 ALREADY RUNNING，不启动第二个队列；若关闭窗口后仍残留本批次工作进程，应先执行 Stop 再 Resume。Stop 精确匹配脚本和批次路径，不会按 Python 进程名批量终止其他任务。

每次续跑均保留带时间戳的计划、控制层代码副本、原始中断输出和冻结批次哈希。前台继续显示完成/失败数、当前解和预计剩余时间。终端应保持开启；退出后使用同一条续跑命令即可。
