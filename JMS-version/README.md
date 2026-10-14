# JMS中英文稿件

中文稿为修改基准，英文稿同步表述与实验结果。当前正文采用“工艺约束—调度模型—求解方法—实验分析”的结构；已删除CIM、MES与控制器集成叙述及商业设备实物图。正文共10张图，后续图号自动顺延。

- `JMS_Review_CN.tex`、`JMS_Review_CN.pdf`：中文核对稿。
- `JMS_Submission_EN.tex`、`JMS_Submission_EN.pdf`：英文稿。
- `output/submission/JMS_Submission_CN.zip`、`JMS_Submission_EN.zip`：中英文同层文件压缩包。
- [MODEL_EXPLANATION_CN.md](MODEL_EXPLANATION_CN.md)：唯一模型说明，按正文顺序解释38个编号公式及关键行内关系，附55行符号的范围和实例，并用真实4片排程串起完整加工过程。

每个压缩包根目录包含正文TeX、正文PDF、Figure1.pdf至Figure10.pdf、Highlights.txt及Declaration_of_Interest.txt，共14个文件。表格、参考文献、作者贡献和其他声明保留在正文中。无子文件夹、嵌套压缩包、日志或作者待办。包内图件路径已调整为根目录，并验证解压后XeLaTeX编译所得文本与主稿一致。

文件结构依据Elsevier官方LaTeX要求：
https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions

在Editorial Manager上传后，将正文、图件、Highlights及声明指定为相应文件类型；如系统单独接收正文PDF，可使用本目录提供的PDF。中文包用于内部核对；英文包用于期刊投稿准备。JMS专属作者指南访问仍受限，文章类型、匿名方式及额外表单应以实时投稿界面为准。作者仍需确认资助信息、作者贡献、原创性及投稿同意。

重新编译及打包：
```powershell
& .\JMS-version\tools\build_submission.ps1 -Python G:\conda\python.exe
```

仅基于当前PDF重新打包：
```powershell
G:\conda\python.exe .\JMS-version\tools\package_submission_bilingual.py
```

`figures/temp/`保留此前8片和24片甘特图及4s交换版本，不收入正文包。原始结果与模型保留在`results/`、`warm_starts/`、`../JMS/results/`和`../cie/results/`。本目录的重复模型说明、历次审查笔记、历史稿件快照和编译缓存已清理；实验目录内的输入、原始结果、验证记录及冻结资产保留。目录外的`../manuscript_archive/`不属于本次清理范围，也不属于投稿文件。

模型符号与中英文一致性检查（不启动实验）：

```powershell
G:\conda\python.exe .\JMS-version\tools\audit_model_notation.py
```

## 已完成的追加结构验证

追加验证的4/6片基准见`results/joint_model/structure_check_20261013_082226/`，独立验解见`results/joint_model_validation/structure_check_20261013/audit.json`。四个结果均通过完整联合模型赋值检查、物流重放、洁净/脏手约束及辅助晶圆复用检查；输入、共同初始赋值及冻结模型与2026-10-11轮次相同，种子均为1。两轮终止上下界相同，因此这一基准轮次属于相同协议的重复运行，不增加独立实例或随机种子样本。

四组基准中，4片固定结构为532 s（上下界一致，45 s结束），联合搜索为717 s、下界46 s；6片固定结构为957 s、下界725 s，联合搜索为1530 s、下界39 s。正文保留这些原始对照值，初始化用时为0.296/0.781 s。原共同初始解下的联合搜索没有改变配对、辅助身份、分腔或周期结构；其结果支持排程可行性、给定预算下的搜索表现和时间优化收益。新的辅助身份结构收益由下面的追加对照单独给出。

两组追加验证均已完成：`results/joint_model/strong_start_20261013_103702/`含4/6片强初始解联合搜索；`results/joint_model/auxiliary_partition_retry_20261013_103715/`含4片辅助身份对照。独立验解见`results/joint_model_validation/followup_20261013/audit.json`，覆盖原四组基准及三组追加结果。

| 追加验证 | 起点/s | 终止下界/s | 可行完工时间/s | 结构与并行 |
|---|---:|---:|---:|---|
| 4片强初始解联合搜索 | 532 | 46 | 532 | 配对、辅助身份、分腔和周期结构不变 |
| 6片强初始解联合搜索 | 957 | 39 | 957 | 配对、辅助身份、分腔和周期结构不变 |
| 4片分腔辅助身份 | 628 | 393 | 403 | CH1借D1/D2、CH2借D3/D4；加工重叠111 s |

三组均采用种子1、追加1800 s主求解并关闭第二阶段。辅助身份对照保持产品结构与8片库存不变，403 s低于原固定结构的已证最优值532 s，缩短129 s（24.25%）；该赋值同时满足完整联合模型。393 s是新固定辅助结构的下界，不是完整联合问题的下界。强初始解验证保留532/957 s，不能用来支持联合搜索或学习选割的性能优势。

预算分开计量：强初始解来自此前45/1800 s固定结构求解；辅助身份初始排程来自60 s预搜索，之后才追加1800 s。新结果作为结构对照加入正文，未替换共同初始解算法比较，也未将同种子重复运行增加为独立实例。正文目前保留107次主实验及7次小规模结构验证。

本次修订同步摘要、模型解释、结构对照表、讨论、结论及中英文Highlights，并删除英文实验指标段中重复的工具使用说明；AI声明保留在文末专门章节。模型说明新增403 s实例及变量变化解释。修订前双语源稿快照与验解结果保存在同一`followup_20261013`验证目录。

计算环境已由作者确认历史实验与当前环境一致：Intel Core Ultra 7 265KF、32 GB内存、RTX 5060 Ti（8 GB显存）、Windows 11，Python 3.12.12、SCIP 10.0.1、PySCIPOpt 6.1.0、PyTorch 2.11.0。处理器、物理内存与软件版本经本机读取，GPU与冻结实验清单交叉核对；已补入双语实验设计。JMS专属作者指南本次访问仍返回403，未依据非官方网页改写投稿要求。

复核这些已完成结果（只验解，不重新优化）：

```powershell
Set-Location D:\git\git\RDMCT-A3C
& G:\conda\envs\a3cenv\python.exe .\JMS-version\tools\audit_structure_supplement.py `
  --campaign .\JMS-version\results\joint_model\structure_check_20261013_082226 `
  --strong-start .\JMS-version\results\joint_model\strong_start_20261013_103702 `
  --witness .\JMS-version\results\joint_model\auxiliary_partition_retry_20261013_103715 `
  --output .\JMS-version\results\joint_model_validation\followup_20261013\audit.json
```

验解核对冻结资产、输入、LP、热启动与变量文件哈希，分别检查未固定的完整联合模型和对应固定结构，并独立重放完整物流与物理手约束。原始结果保持不变。
