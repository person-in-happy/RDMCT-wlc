# 当前默认参数的独立后端

当前补充实验使用[期刊命令](../JOURNAL_EXPERIMENT_COMMANDS.md)或[学位论文命令](../EXPERIMENT_COMMANDS.md)。`paper_defaults.py` 是此前固定资源预算批次的入口，恢复旧批次时保持其冻结协议。本目录从20261102非递减后端独立形成，旧目录和冻结批次保留。

- 工艺腔驻留扣除生产/清洁必要处理时间，默认100 s。
- AL与LL仍限制整个放片结束至取片开始区间；机械手限制完整承片区间，默认均100 s。
- 统一时域10000 s，包含LL复位尾部。时间条件大M取时域加必要间隔上界。
- 新输出模型标记为 `pjob_nondecreasing_nonprocessing_v1`。
- 主排程保留完整候选容量。不自动使用旧的串行构造器或旧固定结构比较入口；当前紧驻留参数不保证其构造排程可行。
- `paper_defaults.py inspect`只检查矩阵；`prepare`只冻结配置/已有合格起点；`run`才启动正式实验。
- `run_experiments.py`是低层求解实现；其他复制的实验入口是依赖文件，不代表其旧参考准备流程已适配当前100 s约束。

历史参数复核与证书位于 [20261103 审查记录](../revisions/20261103_results_default_residency/REVIEW_CN.md)，不能把当时“未运行”的说明当作当前进度。

## 重绘已保存排程

从仓库根目录执行。以下命令读取证书并检查完整赋值、物理重放和哈希，不启动优化：

```powershell
$py = 'G:\conda\envs\a3cenv\python.exe'
$proof = 'JMS-version/revisions/20261103_results_default_residency/optimality_certificate.json'
$certificate = Get-Content -Raw -Encoding UTF8 -LiteralPath $proof | ConvertFrom-Json
& $py -X utf8 '.\JMS-version\tools\render_current_defaults_gantt.py' --result $certificate.result --variables $certificate.variables --proof $proof --output 'JMS-version/figures/current_defaults_20261103' --require-optimal
```

其他排程将 `--result`、`--variables` 和 `--output` 替换为对应独立路径。完整主问题上下界闭合且验解通过时才使用 `--require-optimal`；限时可行解应明确标注未证明最优。旧模型或失配参数的图件不能作为当前配置的实验结果。
