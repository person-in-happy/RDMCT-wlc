# JMS 当前中文稿与实验入口

中文审阅稿的正文、公式、表格和参考文献均在一个主文件中。当前配置 D 使用 Pjob 库存与 PW 对联合模型、非递减取片规则、100 s 非加工驻留与承片上限，以及包含装载锁复位的 10000 s 时域。另一份 `../JMS/` 稿件独立维护。[中文主稿](JMS_Review_CN.tex) · [审阅 PDF](JMS_Review_CN.pdf) · [2026 年 11 月 20 日中文源文件包](output/JMS_Review_CN_source_20261120.zip)

## 当前文档

- 表3的两种批量、统一算例的四种目标方案，以及16片混合初始化和选割对照见[阈值与混合配方实验](results/mixed_controls_20261122/README_CN.md)。
- 中文稿涉及工艺目标的实验采用[产品晶圆等待定义与结果索引](results/product_wait_20261122/README_CN.md)。其中列出按产品路线重算的历史排程、按新目标求解的对照及逐次运行记录。
- [期刊实验命令与状态](JOURNAL_EXPERIMENT_COMMANDS.md)：当前补充实验、已完成结果和条件启动要求。
- [期刊全文审查](JOURNAL_REVIEW_CN.md)：证据边界和待补事项。
- [学位论文实验命令](EXPERIMENT_COMMANDS.md)及[章节与研究整理方案](THESIS_REVIEW_AND_PLAN_CN.md)：同协议结果复用，避免重复运行。
- [模型公式说明](MODEL_EXPLANATION_CN.md)（[PDF](output/pdf/MODEL_EXPLANATION_CN.pdf)）：库存、配对、周期、资源和目标的解释。
- [审查工作流](REVIEW_WORKFLOW.md)：证据核对、验解与文稿交付要求。

## 代码与历史归属

- 当前中文稿的 RL-DMCT 两阶段搜索使用[允许两种末端卸片次序的模型](experiments/terminal_unload_20261125/extended_model.py)和[间隙与停滞节点求解入口](experiments/stall_nodes_20261127/run.py)。从仓库根目录执行下列命令，可从已有排程开始搜索，也可将输入换成含 `load_ports` 的 Pjob 配置。配置输入会构造初解并执行 SPBS，已有排程作为准备好的初解直接进入两阶段搜索。

  ```powershell
  JMS-version/.solver_env/Scripts/python.exe JMS-version/experiments/stall_nodes_20261127/run.py JMS-version/results/terminal_unload_20261125/two_event_replay/H3/schedule.json output/stall_nodes/two
  ```

  A、B 的相对间隙默认分别为 0.01% 和 1%。`--stall-nodes-a`、`--stall-nodes-b` 分别控制两个阶段的连续无改善节点数，初始设定均为 1000，取 `-1` 关闭对应阶段的停滞条件。要限制根节点等耗时较长的搜索，可另设 `--seconds-a`、`--seconds-b`，单位为 SCIP 搜索秒，初始化与验解时间另计。第一阶段默认开放完整候选域。使用 `--use-input-candidate-limits` 可显式保留输入中的候选上限，此时按记录的求解范围解释上下界。

  同一条命令可从已验证的阶段终点续跑。中断的阶段从该阶段输入重新建立搜索树，已用的阶段搜索时间从指定预算中扣除。前台和 `status.json` 显示进度与估时依据。`A/record.json` 和 `B/record.json` 分别保存实际触发原因、可行上界、对偶或解析下界、实际间隙、节点数和验证结果。最终排程在 `B/schedule.json`。
- [当前默认参数后端](model4_pjob_nonprocessing_20261103/README_CN.md)提供完整配置 D 的设备与工期模型。新工艺目标实验用[目标与事件计分实现](experiments/product_wait_20261122/objective.py)建立产品等待项，使用[实验入口](experiments/product_wait_20261122/run.py)。旧批次内置的全晶圆等待目标仅供复现历史运行。
- `model4_pjob_nondecreasing_20261102/`：此前非递减实现，配置和预算按冻结批次解释。
- [严格取片后端](model4_pjob_fifo_20261029/README.md)、[早期 Pjob 后端](model4_pjob_20261027/README.md)：历史模型与复现依赖。
- `joint_model/`、`model2_compact_20261025/`、`model2_lowmem_20261026/`：逐片联合模型及等价/低进程内存实现。
- `heterogeneous_model_20261022/`：异质时长扩展，构造可行解不能当作当前 D 模型最优解。
- [可行取放序列](gif/kexingyu/README.md)：构造序列及数量下界，按子目录模型归属使用。
- `review/`、`revisions/`、`results/`：审查记录、修改前原稿、冻结协议、解和验证证据。

## 运行与构建

实验在可见前台终端启动，使用各命令文档指定的独立目录。先检查已有批次，避免重复启动；活动实验只读检查，恢复时保持原冻结配置。超时无可行解不是不可行性证明。

从仓库根目录构建当前中文稿：

```powershell
G:\conda\python.exe -X utf8 JMS-version/tools/build_model4_cn.py
```

英文稿、Highlights 和英文投稿包对应 2026 年 11 月 17 日的固定预算版本。正式投稿前需同步本版中文稿的标题、按间隙控制的两阶段求解结果和七幅图。英文包的构建入口为 `tools/build_submission_en.py --render-docx`。[英文稿](JMS_Submission_EN.tex) · [英文投稿包](output/submission/JMS_Submission_EN.zip) · [上传说明](output/submission/UPLOAD_README.txt) · [翻译记录](submission/README.md)

大型原始实验和冻结资产按原策略保留本地。整理稿件时保留原始证据和活动批次。
