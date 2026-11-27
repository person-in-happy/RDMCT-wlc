# JMS 英文投稿稿审查记录

2026 年 11 月 27 日。英文主稿为 [JMS_Submission_EN.tex](../JMS_Submission_EN.tex)，预览见[投稿 PDF](../output/submission/JMS_Submission_EN.pdf)，源文件、图件和投稿附件见[完整交付包](../output/submission/JMS_Submission_EN.zip)。

## 稿件与研究证据

C&IE 两稿的摘要和结论沿用各自期刊版本，方法与实验正文已同步本轮术语、交叉引用及表 3 的修订。JMS 中文稿保留作者给定的摘要，结论首段说明生产补位、清洁与末端卸片的设备背景。JMS 英文稿依照[现行中文稿](../JMS_Review_CN.tex)修订。两轮中文底稿分别见[期刊分稿时快照](../revisions/20261126_journal_sync/JMS_Review_CN.before.tex)和[本轮文字精修前快照](../revisions/20261126_prose_grid/JMS_Review_CN.tex)。

| 审查项 | 核定结果 |
|---|---|
| 目标含义 | Batch makespan 是最后一片产品回到原装载端口的时刻。设备释放还需等待末端清洁、辅助片归还或装载锁复位。Process objective 以等效秒计，包含平均腔内非加工驻留、同配方最大驻留极差的平方惩罚，以及实际清洁时距污染阈值尚余周期数的加权和。 |
| 小批次下界 | 允许两种合法末端卸片次序时，2 片（H=3）、4 片和 8 片（H=3 或 10）等量混合实例分别达到 (324, 3)、(397, 3)、(552, 3)。常规卸片的连续曲线在正文和图题中有单独的适用范围。 |
| 16 片对照 | 常规卸片、H=10、总加工时间均为 810 s。三个求解种子配对后，仅优化总加工时间的工艺目标均值为 2681，两阶段为 934.5 等效秒。降幅 (2681−934.5)/2681 为 65.14%。 |
| 4 片消融 | 匹配预算、三个种子的平均总加工时间分别为 HEM 403 s、完整法 398 s、关闭候选割重排 403.67 s、移除初解分层改进 406.33 s。五种 2 片配置的 45 组另行对照均与 HEM 持平。 |
| 甘特图与规模 | 4 片纯并行实例在 397 s 回片时工艺目标为 0。16 片纯并行实例在 896 s 回片时工艺目标为 78 等效秒。75 片混合实例在 6050 s 回片、6533 s 释放设备，图中排程的工艺目标为 1366.69 等效秒。按作者要求仅替换图件，正文保留前一排程的工艺目标 1417.35 等效秒及其驻留与等待统计。在两腔首次并行工艺加工结束时刻固定时，CH2 与 CH3 至第二次同工艺加工开始的间隔从 313、257 s 缩短至 280、234 s。保留原实例和腔室周期安排，局部调整搬运次序所得的可行排程满足原模型全部 24,271,470 行约束。表 6 末行的 75 片采用另一端口供片配置。 |
| 方法与可复现性 | 正文交代分层初解、选割、两阶段的求解范围、停止条件及训练实例构成。随稿补充 ZIP 含 108 项阈值记录、两份训练日志与检查点标识。 |

[小批次下界与事件重放](../review/reviewer_20261125/README_CN.md) · [16 片配对目标比较](../results/square_table4_20261125/publication.json) · [4 片逐种子消融](../results/square_residence_20261125/table5/table5_seeds.csv) · [英文补充数据](../output/submission/Supplementary_Data.zip)

## 期刊格式与材料

- JMS 官方指南存档采用单匿名审稿。正文保留署名与通讯作者信息。英文摘要 232 词，独立定义 HEM，六个关键词。文献按正文首次引用顺序以方括号编号。31 条题录均已与 DOI 登记或原会议记录核对。4 条可编辑 Highlights 各含 79、77、81、76 个字符（含空格）。[JMS 官方指南存档，2024-04-14](https://web.archive.org/web/20240414172303/https://www.sciencedirect.com/journal/journal-of-manufacturing-systems/publish/guide-for-authors) · [Elsevier 当前 Highlights 说明](https://www.elsevier.com/researcher/author/tools-and-resources/highlights)
- 稿件嵌入公式、表格和图。源包平铺一个 TeX 文件和九个矢量图件，图 3 包含两个面板。利益冲突文件使用指南链接的出版社 Word 模板，按中文声明选中无已知利益冲突。CRediT、资助、通讯邮箱、数据可用性和 AI 使用披露均与中文稿核对。本轮英文图件重排原矢量图中文字，核验了图形及事件记录。[Elsevier LaTeX 说明](https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions) · [官方利益冲突模板](https://legacyfileshare.elsevier.com/promis_misc/declaration-of-competing-interests.docx) · [AI 政策](https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals)
- JMS 将制造系统层面的问题列入范围，同时说明一般车间调度与资源优化通常不属其范围。投稿信据实际证据说明同一设备内工艺腔、机械手和辅助片为何必须联合调度，以及卸片次序如何改变产品回片与设备释放。工业现场实施或良率改善未列入贡献，期刊契合度由编辑判定。[JMS 官方范围](https://shop.elsevier.com/journals/journal-of-manufacturing-systems/0278-6125)
- 2026 年 11 月 26 至 27 日访问 JMS 现行作者指南返回 HTTP 403。已核对 2024 年官方全文存档及现行出版社公开说明。指南存档要求推荐 5 位审稿人，提供地址、邮箱、适任理由，并核实利益冲突。现有文件没有作者确认的人选；投稿时由通讯作者按系统当时字段填写，并完成独家投稿、共同作者批准和印刷彩色偏好等声明。[JMS 现行指南入口](https://www.sciencedirect.com/journal/journal-of-manufacturing-systems/publish/guide-for-authors) · [官方投稿系统](https://www.editorialmanager.com/smejms/)
- C&IE 投稿稿使用匿名正文和独立标题页，正文采用 APA 7 作者—年份引文。两刊格式与文件入口见 [C&IE 审查记录](../../cie/products/CIE_CURRENT_REVIEW_CN.md)。

## 构建与核验

JMS 中文 17 页、英文 20 页。中英文 38 组编号公式、1 组未编号界式、4 张结果表全部 53 行数值、72 个标签及 31 篇参考文献完成对照。两张符号表另保留符号和定义。表 3 位于中文第 11 页和英文第 13 页，均占一栏。表 3 的 36 行各对应一种片数、工艺与第一阶段阈值组合，每行并列总加工时间及三个工艺目标值，全部 144 个结果单元格根据 108 条阈值记录保留两位小数。中文公式编号引用从 38 处减至 11 处，20 处章节回指已删除。英文正文共 8 幅图、9 个图件。两稿最终日志均无未定义引用、缺字或越出版心报告。五份 Word 附件均经 Microsoft Word 渲染为单页。英文平铺源包经独立编译，逐页提取文字与交付 PDF 一致。见[翻译检查](translation_checks.json)、[编译与源包核验](validation.json)和[视觉检查](visual_review.json)。

从仓库根目录运行 `python -X utf8 JMS-version/tools/build_submission_en.py --render-docx` 可重建 JMS 英文稿及其附件。装配器从中文源稿取得参考文献，将[英文正文](manuscript_body_en.tex)和[英文首页与声明](manuscript_frame_en.tex)合为独立主文件。中文内容变动后，需核对译文再更新装配器的审阅哈希。本轮工艺目标的[去除清洁项复算](../review/prose_grid_20261126/effect_of_E.json)与[三张甘特图的局部优化及可行性核验](../results/chamber_wait_20261126)保存在审查目录和结果目录中。
