# JMS 投稿适配与引文核查

审查日期：2026-09-05（Asia/Shanghai）。审查对象：`JMS_Review_CN.tex`。本文件独立于正文，记录事实核查、审稿判断和未验证事项；不表示已完成投稿或所有作者已批准稿件。行号参考审查开始时稿件，后续编辑可能使行号变化。

## 1. 最重要的投稿判断

**已核实的事实：**稿件明确写明目标期刊为 *Journal of Manufacturing Systems*（JMS，ISSN 0278-6125）。Elsevier 官方期刊介绍接受从装备层到扩展企业的制造系统研究，也列出制造业人工智能和物流等主题；但同时明确把通常的车间调度、建模与仿真、资源优化等列为一般不在范围之内的主题。

来源：[Elsevier 官方 JMS 介绍](https://shop.elsevier.com/journals/journal-of-manufacturing-systems/0278-6125)，访问于 2026-09-05。

**审稿判断：**现稿存在明显初筛风险。模型加学习选割的小幅性能提升，本身不足以消除这一风险；标题和正文频繁使用“系统级”也不是适配证据。最有说服力的核心应是双源物流、满片约束、辅助晶圆复用、清洗和共享机械手共同造成的设备运行机制，并用可检查的设备事件与资源占用证据说明它们不能被独立优化。8/16 片清洗间隔实验有助于补充这一系统机制，长时限求解主要补充求解证据，两者均不能替代工业来源或实机验证。

**不能确认的事项：**没有仅凭本次只读稿件就确认设备参数来自工业现场、模型已在实机执行、可提高实际良率或全厂产能。不能用这类表述补强期刊适配。若缺少实机数据，应明确定位为基于给定设备结构的计算研究。

## 2. 作者指南核查边界

已尝试官方入口：

- [JMS Guide for Authors](https://www.sciencedirect.com/journal/journal-of-manufacturing-systems/publish/guide-for-authors)。
- [JMS Aims and Scope](https://www.sciencedirect.com/journal/journal-of-manufacturing-systems/about/aims-and-scope)。
- [Elsevier 旧版官方作者指南入口](https://www.elsevier.com/journals/journal-of-manufacturing-systems/0278-6125/guide-for-authors)。

2026-09-05 访问返回 403 或获取失败，因此**未核实** JMS 当前英文摘要限字、页数/字数限制、图文摘要是否必需、Highlights 是否必需以及当前期刊专属数据共享政策。不应将第三方模板描述冒充官方硬性要求。

出版方通用规则可核实：Highlights 通常使用 3–5 条，每条最多 85 字符（含空格），单独提交可编辑文件；但是否必需取决于具体期刊指南。来源：[Elsevier Highlights 帮助页](https://www.elsevier.support/publishing/answer/how-do-i-include-highlights-with-my-manuscript)，页面更新 2026-06-01，访问 2026-09-05。

稿件已有 CRediT、利益冲突、数据代码和生成式 AI 声明。需作者在正式提交前核实作者贡献、资助和全体作者批准情况；“正式发表版将给出永久公共归档地址”目前是承诺，不是已存在的归档证据。中文审阅稿也不等于已完成可提交英文稿。

检索出现的 `sciencedirectelsevier.com` 不是本次使用的 Elsevier 官方证据来源，未采信其期刊数据或指南。

## 3. 建议立即修订的引文与论断

|位置/主题|发现及依据|建议|
|---|---|---|
|引言约 87–91 行|“最重要的三个环节”“传统 CT 已经无法满足 PECVD”均缺少足以支持这一行业范围结论的来源。Gu 2024 支持多空间、多指机械手及旋转访问结构，不支持全部传统 CT 无法满足 PECVD。|改为“薄膜沉积等工艺对设备吞吐和空间利用率提出要求，部分设备采用多空间旋转腔”等限定表述。|
|约 93–97 行，满片必要性|Gu 2024 的公开原文可支持四空间和内部旋转，不能据此确认本稿含碳薄膜、空工位保护、独立真空辅助源的全部物理设计。|把满片和双源辅助库存写成本研究对象的设备/工艺假设，说明工业规格、专利或现场资料来源；没有来源时不扩展为行业普遍事实。|
|引言研究空白|引用的若干论文没有覆盖本稿组合问题，不等于已证明全部文献不存在此类研究。|用“上述研究尚未同时覆盖本文关注的……”而不是无保留的优先性断言。|
|HEM 2023 参考文献|正文仅有这一项 Wang 2023，但 `bibitem` 和年份手工保留了 `2023b`。原始论文为 ICLR 2023。|去掉孤立的 b；如之后确实加入同作者同年项目，再由参考文献样式生成后缀。|
|HEM 研究更新|直接前身在 2024 年已有 TPAMI 扩展版，见下一节。|补引，并明确 HEM-13D 是与 2023 序列实现对应的受控复现；不要暗示比较覆盖扩展版所有模型。|
|约 552–602 行，角色特征|正文称特征只读取变量类型、目标系数和全局界，不读取设备标签。因而这是模型变量角色结构，不是直接识别机械手/腔室/清洗等物理资源语义。|用“变量角色感知”“数学模型结构”限定机制；把物理含义作为特定模型上的解释，而不是已经验证的语义识别能力。|
|约 704 行，统计引用|MIPLIB 2017 原文公开全文检索没有 Wilcoxon、Holm 或 bootstrap，不能支撑所列统计方案的出处。|删除该句对 MIPLIB 的引文，或挪到实例多样性、基准记录与复现讨论。统计方案可作为本研究预设分析方法直接说明，若需要方法引用则引对应原始来源。|
|约 799 行和结论|相对 HEM 的 PDI 1.41%、时间 0.61%、终止 gap 0.97% 为均值差。未看配对显著性/置信区间前不能把所有方向一致的均值差写成已确证稳健优势。|明确“观察均值”；区分均值改善、统计证据与实际制造收益。|
|约 828–838 行 OOD|729 次都有解归属于共同 SPBS–MILP–SCIP 链路；完整方法 OOD 平均 PDI 劣于纯 SCIP，简单评分变体更好。|保留这一反向证据，不能把共同可行率归因为学习模型泛化优越。|
|“无死锁”和“精确”|数学可行排程及 SCIP 验解不自动等于在任意现场扰动下无死锁，也不自动等于无浮点误差的形式化证书。|限定为模型假设、给定事件时序、容差下的可行性/最优性状态；交代在线执行、故障、随机到达未验证。|

物理拓扑依据：[Gu et al., Applied Sciences 2024](https://www.mdpi.com/2076-3417/14/20/9490)，DOI 10.3390/app14209490，访问 2026-09-05。

统计引用依据：[MIPLIB 2017 原始论文](https://link.springer.com/article/10.1007/s12532-020-00194-3)，访问 2026-09-05。此处检索缺词仅用于指出未找到统计方案支撑，并非声称该文否定这些统计方法。

## 4. 抽查的近期文献

|文献键|核查结果|一手来源（均访问 2026-09-05）|
|---|---|---|
|`gu2024applied`|题名、五位作者、2024 年 14(20):9490、DOI 匹配；公开全文支持四空间、两面访问、腔室旋转与 LP 稳态周期分析。|[出版社全文](https://www.mdpi.com/2076-3417/14/20/9490)|
|`wang2025virtualcell`|2025 年卷 22:240–251 与作者机构记录一致；2024 是在线发表年/DOI 年份，不能据 DOI 年份判本稿 2025 错误。摘要支持同时选择 PM 数量与机械手等待。|[IEEE DOI 页面](https://doi.org/10.1109/TASE.2024.3349380)、[作者机构 NJIT](https://researchwith.njit.edu/en/publications/virtual-cell-based-scheduling-approach-to-single-robotic-arm-clus/)|
|`yang2025miptwowafers`|作者、2025 年卷 288:128209 和 DOI 匹配；摘要/Highlights 支持联合优化两类晶圆投放与机器人任务序列。|[ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0957417425018299)|
|`kim2025adaptivecluster`|作者、2025 年卷 22:3783–3796 和 DOI 匹配；处理不预设循环的两种晶圆调度，摘要支持强化学习及自适应搜索。|[作者机构 KAIST](https://pure.kaist.ac.kr/en/publications/scheduling-cluster-tools-for-concurrent-processing-deep-reinforce/)|
|`kim2025noncyclicdeadlock`|2025 年卷 22:24009–24023、作者、DOI 均与机构记录一致；摘要明确动态解码机器人动作并避免死锁。|[作者机构 KAIST](https://pure.kaist.ac.kr/en/publications/noncyclic-scheduling-of-cluster-tools-using-deep-reinforcement-le/)|
|`hong2026ddpgct`|2026 年卷 211:111698 与 DOI 2025 年份并不矛盾。公开摘要明确 DES + DDPG 调节 PVD 工艺时间；稿件对此定位基本准确。|[ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0360835225008447)|
|`zhu2025failuredeadlock`|本次 IEEE 一手入口获取失败，**未独立完成内容核查**；检索书目与稿件 DOI/年份/页码一致，不能用相似题名 2026 双臂论文代替原文。|[待访问 IEEE DOI](https://doi.org/10.1109/TASE.2023.3275703)|

补充检索发现 [Zhu et al. 2026 双臂两组合设备故障调度](https://www.sciencedirect.com/science/article/pii/S0957417425030313)，DOI 10.1016/j.eswa.2025.129415，297 Part C:129415。其出版社摘要明确把共享缓冲死锁避免纳入故障关机模型。这是与本稿故障/在线边界相关的可选更新，并非必须为了增加新年份而添加的引用；本稿未处理故障，不能借此暗示具备故障恢复能力。

## 5. 学习选割原始来源与可复现边界

- Tang, Agrawal, Faenza (2020), *Reinforcement Learning for Integer Programming: Learning to Cut*, ICML / PMLR 119:9367–9376。原始出版页：[PMLR](https://proceedings.mlr.press/v119/tang20a.html)。现稿“将选割写成强化学习策略”基本准确。
- Huang et al. (2022), *Learning to select cuts for efficient mixed-integer programming*, Pattern Recognition 123:108353。原始出版页：[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0031320321005331)，[作者机构可访问稿件](https://discovery.ucl.ac.uk/id/eprint/10154111/)。现稿“学习候选割排序”基本准确；其核心包括 multiple instance learning，而不只是逐割监督标签。
- Paulus et al. (2022), *Learning to Cut by Looking Ahead: Cutting Plane Selection via Imitation Learning*, ICML / PMLR 162:17584–17600。原始出版页：[PMLR](https://proceedings.mlr.press/v162/paulus22a.html)。题名、作者、页码与前瞻模仿定位匹配。
- Wang et al. (2023), *Learning Cut Selection for Mixed-Integer Linear Programming via Hierarchical Sequence Model*, ICLR 2023。原始作者稿：[arXiv:2302.00244](https://arxiv.org/abs/2302.00244)；[官方代码](https://github.com/MIRALab-USTC/L2O-HEM-Torch)；[OpenReview](https://openreview.net/forum?id=Zob4P9bRNcK)本次需要浏览器验证。官方代码也区分求解器种子和 Python/PyTorch 种子，基线复现应记录两类随机性。
- Jie Wang, Zhihai Wang, Xijun Li, Yufei Kuang, Zhihao Shi, Fangzhou Zhu, Mingxuan Yuan, Jia Zeng, Yongdong Zhang, Feng Wu (2024), *Learning to Cut via Hierarchical Sequence/Set Model for Efficient Mixed-Integer Programming*。原始作者稿：[arXiv:2404.12638](https://arxiv.org/abs/2404.12638) / [可检索全文](https://arxiv.org/html/2404.12638v1)；[作者官网](https://zhihaiwangx.github.io/)与[实验室发表消息](https://miralab.ai/news/)确认正式 TPAMI 2024 版本。正式 DOI：[10.1109/TPAMI.2024.3432716](https://doi.org/10.1109/TPAMI.2024.3432716)。本次 IEEE DOI 入口失败，卷页 46(12):9697–9713 仅被检索书目交叉支持，正式参考文献导入时宜由作者再取出版社 BibTeX 核对。

以上来源均于 2026-09-05 访问。HEM 扩展版的存在是可核实事实；“必须新增一组长期重训实验才能投稿”不是本次审查结论。当前可立即完成的是补引、明确比较覆盖范围并约束优越性主张。

## 6. 与运行中实验的关系

引文纠错、范围限定、投稿风险说明和方法归属澄清均不必等待实验。涉及清洗间隔作用方向、所有 8/16 片组合的最优 Cmax、长时限下从无 incumbent 到找到解/证明最优的比例，必须等对应运行结束并通过实例与参数对齐后再报告。不得把进行中的部分日志当成完整实验，或以长时限重跑结果替换固定 600 s 公平预算下的原始性能结论。
