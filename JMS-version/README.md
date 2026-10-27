# JMS项目：采用模型2

项目采用同质工艺加工时间、允许阈值前清洁且达到阈值必须清洁的联合模型。模型说明以论文正文为准，不再维护独立的重复说明文档。

- 中文主稿：`JMS_Review_CN.tex`、`JMS_Review_CN.pdf`；英文稿：`JMS_Submission_EN.tex`、`JMS_Submission_EN.pdf`。
- `joint_model/`：模型2原事件实现、物理验解和原实验接口。
- `model2_compact_20261025/`：模型2等价紧凑实现及测试；续跑协议仍依赖该目录。
- `model2_lowmem_20261026/`：当前低进程内存入口；活动DOE批次保持原设置。
- `heterogeneous_model_20261022/`及`results/heterogeneous100_80_180_90_20261022/`：模型3后续工作，保留代码、配置、冻结资产和结果。100片现有记录是构造可行上界，尚未证明最优，不作为模型2实验结果。
- `gif/kexingyu/`：模型2可行取放序列及验证证据；Git保存无损压缩文本，使用该目录简化版说明读取。

模型1的旧图和中间导出仅在未被当前论文、热启动和图件重建引用时删除。仍被直接使用的原始排程、图源、数值结果、冻结模型及检查点保留。不同资源协议的结果不混作同一预算的性能样本。

## 运行

从仓库根目录执行环境与资源检查：

```powershell
G:\conda\envs\a3cenv\python.exe -X utf8 JMS-version/model2_lowmem_20261026/low_memory_evidence.py check
```

现有批次运行时不要重复启动。恢复批次使用同一入口的`resume --campaign <目录>`，先确认父进程及工作进程均已退出。队列以前台方式显示进度，超时不表示不可行或最优。

稿件编译入口为`tools/build_submission.ps1`，中英文打包入口为`tools/package_submission_bilingual.py`。审稿证据规则见`REVIEW_WORKFLOW.md`。

## 版本管理

大型原始实验和活动批次保留本地，沿用不提交原始求解资产的策略。Git提交模型代码、测试、现行稿件、必要图源、压缩可行序列及模型3已有成果。清理清单见`cleanup_20261027.json`；本轮未修改活动模型2实验的代码和冻结输入。
