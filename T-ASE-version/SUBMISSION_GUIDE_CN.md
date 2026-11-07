# T-ASE 转投核对与修改记录

核对日期：2026-09-15。对象是 IEEE Transactions on Automation Science and Engineering（T-ASE），不是航空航天期刊 TAES。

## 官方要求与处理

| 事项 | 官方依据 | 本次处理 |
|---|---|---|
| IEEE 双栏、数字引用、摘要不超过 200 词 | [作者指南](https://www.ieee-ras.org/publications/t-ase/information-for-authors-t-ase/) | 使用 IEEEtran journal 和 IEEEtran BibTeX 样式；英文主稿 12 页，词数见检查报告 |
| 摘要后 100–300 词 Note to Practitioners | [NtP 指南](https://www.ieee-ras.org/publications/t-ase/information-for-authors-t-ase/t-ase-note-to-practitioners/) | 新写输入、用途、实施条件及适用限制，区别于摘要 |
| 双匿名，正文、补充材料及投稿信不得暴露身份 | [新投稿检查表](https://www.ieee-ras.org/publications/t-ase/information-for-authors-t-ase/author-checklist-for-papers-submitted-to-ieee-t-ase/)和[匿名规则](https://www.ieee-ras.org/publications/rules-for-the-double-anonymous-review-process/) | 删除作者、单位、邮箱、CRediT和个人/基金致谢，清空PDF作者元数据 |
| 自动化问题贡献、已有方法数值比较、近两年相关研究 | [新投稿检查表](https://www.ieee-ras.org/publications/t-ase/information-for-authors-t-ase/author-checklist-for-papers-submitted-to-ieee-t-ase/) | 强化资源协调与有限批次模式选择；从冻结记录补入七方法完整表；保留2024–2025相关文献 |
| AI 生成内容说明，注明工具、位置和程度 | [RAS AI 使用规则](https://www.ieee-ras.org/publications/guidelines-for-generative-ai-usage/) | 匿名 Acknowledgment 说明文本重组、翻译、代码及绘图辅助；不替作者声称已经完成最终审阅 |
| 投稿信写明主要/次要方法与应用领域 | [官方分类](https://www.ieee-ras.org/publications/t-ase/information-for-authors-t-ase/t-ase-journal-primary-methodologies-and-applications/) | 草稿使用方法16 Scheduling and Planning、13 Optimization；应用 Semiconductor Manufacturing、Manufacturing |

一般 IEEE 摘要说明给出150–250词，T-ASE页面专属要求为最多200词，本版采用共同满足的150–200词范围。官网超页说明存在“超过12页”和“前10页以后”的历史冲突，Style段又写超过12页按175美元/页收费。本版以12页为控制目标，不对最终收费作保证；最终排版页数和实际系统规则仍需核对。

投稿入口：[IEEE Author Portal](https://ieee.atyponrex.com/submission/dashboard?journalCode=T-ASE)。

## 实质修改

1. 不改写JMS原稿。正文保留完整物理模型的主要约束；符号表、网络展开和训练细节另列英文补充材料。
2. 将成果中心放在双源协调、完整链清洁边界和等待精修。学习选割均值差异小且未显著，不将其包装为显著超越现有方法。
3. 补入冻结Main全部七方法的2700行汇总；配置SCIP在最优率与终止gap上更好，完整方法的PDI与求解时间观测均值更低，均如实呈现。
4. 明确两套实例配置。模式研究的180对90+90秒、10000秒驻留上限，与算法基准的标称180对180+180秒、500秒驻留上限不同，不能交叉推断。
5. 标记SCIP为根节点割分离条件下的受控基线。该标签比“未经配置的默认求解器”更准确。
6. 新写实践说明，限定离线候选排程用途；不新增MES集成、实机部署、随机扰动恢复或薄膜质量验证主张。
7. 主稿合并重复网格行，移除重复甘特图和与表格相同的柱状图；重绘横向设备拓扑，甘特图以双栏宽度保证约8pt以上图内文字。

## 已核实与局限

- 本次读取了六组正式审计JSON：Main2700、Stability1500、DOE300、SPBS960、Sensitivity80、OOD729，均记录ok=true。Validation4和全部6041个incumbent的历史独立验解结论见现有冻结审计。这次没有重新验解6041个解，也没有重新训练或重新跑6273次实验。
- 对照已有冻结LP哈希抽查了16片链式core实例，并读取实际配置及目标约束。完整15个checkpoint的SHA-256在补实验计划检查中通过。
- 核对了近期T-ASE文献的作者机构/出版元数据，包括[非周期调度](https://koasas.kaist.ac.kr/handle/10203/337389?mode=full)和[并行处理DRL](https://cnu.elsevierpure.com/en/publications/scheduling-cluster-tools-for-concurrent-processing-deep-reinforce/)。没有声称重新逐篇阅读全文或重新核实全部历史引用。
- 现有参考文献中的2024 HEM sequence/set版本保留为arXiv，未假定它等于本稿重现的2023 HEM模型。
- 中文稿是完整内部核对版本，英文正文为压缩投稿版本；请结合补充材料核对，不要把中文PDF当作可上传的英文正文。

## 上传前由作者处理

- 核对全部作者对最终版本的同意、作者顺序、ORCID及系统元数据。
- 若JMS稿件已经提交且仍在审稿，先完成撤稿；若只是准备投稿则无需撤稿。当前会话未提供JMS在审状态，不替作者作独家投稿声明。
- 检查资助、利益冲突、潜在既有论文/会议论文重叠；有重叠在匿名投稿信中说明。
- 如提供代码/数据评审链接，先匿名化并检查链接、图件及文件元数据。
- 按EXPERIMENTS_CN.md决定是否补证据；未完成实验不得填入结论。

