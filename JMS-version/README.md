# JMS 当前中文稿与实验入口

当前中文主稿是 [JMS_Review_CN.tex](JMS_Review_CN.tex)（[PDF](JMS_Review_CN.pdf)）。当前配置 D 使用 Pjob 库存与 PW 对联合模型、非递减取片规则、100 s 非加工驻留/承片上限，以及包含装载锁复位的 10000 s 时域。英文稿与 `../JMS/` 中的另一份稿件不自动同步。

## 当前文档

- [期刊实验命令与状态](JOURNAL_EXPERIMENT_COMMANDS.md)：当前补充实验、已完成结果和条件启动要求。
- [期刊全文审查](JOURNAL_REVIEW_CN.md)：证据边界和待补事项。
- [学位论文实验命令](EXPERIMENT_COMMANDS.md)及[章节与研究整理方案](THESIS_REVIEW_AND_PLAN_CN.md)：同协议结果复用，避免重复运行。
- [模型公式说明](MODEL_EXPLANATION_CN.md)（[PDF](output/pdf/MODEL_EXPLANATION_CN.pdf)）：库存、配对、周期、资源和目标的解释。
- [审查工作流](REVIEW_WORKFLOW.md)：证据核对、验解与文稿交付要求。

## 代码与历史归属

- [当前默认参数后端](model4_pjob_nonprocessing_20261103/README_CN.md)：完整配置 D 模型；当前批次由上述期刊/学位论文入口组织。
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

英文稿未同步期间，不使用旧双语打包流程生成当前中文稿的双语投稿包。大型原始实验和冻结资产按原策略保留本地，不得为整理目录删除原始证据或改写活动批次。
