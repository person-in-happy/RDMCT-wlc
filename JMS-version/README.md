# JMS项目：模型4中文稿与模型2冻结实验

中文主稿采用Pjob批次任务表示，保留同质工艺时长及阈值前可选清洁规则。2026-10-29进一步确认全Pjob跨LP严格按序取片，输入编码为批次内第k片产品，算法末端恢复实际晶圆。原330个可行记录中305个通过新顺序复核，24组阶段内精修数值可复用；旧求解成功率和模式排名已从正文撤下。正文不使用内部模型编号。英文稿未同步。

- [本次编码与严格顺序审阅](revisions/20261029_pjob_index_encoding/REVIEW_CN.md)：结果复核、证据复用与修改记录。
- [当前补充实验命令](MODEL4_EXPERIMENT_COMMANDS.md)：新约束下主要156次；学习选割比较另72次。本轮未启动实验。
- [当前模型公式说明](MODEL_EXPLANATION_CN.md)（[PDF版](output/pdf/MODEL_EXPLANATION_CN.pdf)）：对应全Pjob非递减取片版本，解释库存选择、对内位置对应晶圆的完整排程、同刻晶圆身份解码、配对、周期、清洁、资源、两阶段目标及历史构造下界，并标注当前代码位置。

- 中文主稿：`JMS_Review_CN.tex`、`JMS_Review_CN.pdf`；英文稿：`JMS_Submission_EN.tex`、`JMS_Submission_EN.pdf`。
- `joint_model/`：模型2原事件实现、物理验解和原实验接口。
- `model2_compact_20261025/`：模型2等价紧凑实现及测试；续跑协议仍依赖该目录。
- `model2_lowmem_20261026/`：逐片模型的低进程内存入口，保留原有批次与冻结记录。
- [`model4_pjob_fifo_20261029/`](model4_pjob_fifo_20261029/README.md)：当前全Pjob严格出片实现及前台实验入口。
- [`model4_pjob_20261027/`](model4_pjob_20261027/README.md)：此前仅按任务--LP组排序的实现，活动旧队列继续使用，保留冻结记录。
- `heterogeneous_model_20261022/`及`results/heterogeneous100_80_180_90_20261022/`：模型3后续工作，保留代码、配置、冻结资产和结果。100片现有记录是构造可行上界，尚未证明最优，不作为模型2实验结果。
- [`gif/kexingyu/`](gif/kexingyu/README.md)：当前模型4可行取放序列及数量下界，含8/16/32片和四配置合并去重口径；模型2历史序列保留原归属。
- `tools/model4_feasible_orders.py`：Pjob构造、取放输出和任意记录提取验解，不是完整MILP求解器。
- [先前实验复用审计](revisions/20261027_model4/EXPERIMENT_REUSE_AND_RERUN_CN.md)：保留当时尚未实现模型4后端的审计记录；当前执行命令以上述模型4命令文档为准。
- `revisions/20261027_model4/`：中文原稿备份、修改差异、哈希和独立导出审计。

模型1的旧图和中间导出仅在未被当前论文、热启动和图件重建引用时删除。仍被直接使用的原始排程、图源、数值结果、冻结模型及检查点保留。不同资源协议的结果不混作同一预算的性能样本。

## 运行

从仓库根目录执行环境与资源检查：

```powershell
G:\conda\envs\a3cenv\python.exe -X utf8 JMS-version/model2_lowmem_20261026/low_memory_evidence.py check
```

现有批次运行时不要重复启动。恢复批次使用同一入口的`resume --campaign <目录>`，先确认父进程及工作进程均已退出。队列以前台方式显示进度，超时不表示不可行或最优。

当前仅编译模型4中文稿：`G:\conda\python.exe -X utf8 JMS-version/tools/build_model4_cn.py`（从仓库根目录执行）。原`tools/build_submission.ps1`及`tools/package_submission_bilingual.py`用于中英文一致的旧流程；英文未同步期间不能据其生成模型4双语投稿包。审稿证据规则见`REVIEW_WORKFLOW.md`。

## 版本管理

大型原始实验和活动批次保留本地，沿用不提交原始求解资产的策略。Git提交模型代码、测试、现行稿件、必要图源、压缩可行序列及模型3已有成果。清理清单见`cleanup_20261027.json`；本轮未修改活动模型2实验的代码和冻结输入。
