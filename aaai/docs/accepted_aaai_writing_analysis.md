# 往届 AAAI 录用论文的写作逻辑与本稿改写准则

更新日期：2026-07-06

## 1. 精读样本

本次只选取 AAAI 官方 Proceedings 中与“学习辅助优化、MILP、强化学习、调度”直接相关的论文，而不是泛泛模仿某种英文文风。

1. [Fast Approximations for Job Shop Scheduling: A Lagrangian Dual Deep Learning Method（AAAI-22）](https://ojs.aaai.org/index.php/AAAI/article/view/20685)
2. [Reinforcement Learning for Branch-and-Bound Optimisation Using Retrospective Trajectories（AAAI-23）](https://ojs.aaai.org/index.php/AAAI/article/view/25521)
3. [LIMIP: Lifelong Learning to Solve Mixed Integer Programs（AAAI-23）](https://ojs.aaai.org/index.php/AAAI/article/view/26086)
4. [Accelerating Cutting-Plane Algorithms via Reinforcement Learning Surrogates（AAAI-24）](https://ojs.aaai.org/index.php/AAAI/article/view/30067)
5. [Generative Branching for Mixed-Integer Linear Programming（AAAI-26）](https://ojs.aaai.org/index.php/AAAI/article/view/38450)

这些论文用于提取“如何组织技术论证”，不复制其句子或宣称本项目具备它们已经验证的性能。

## 2. 这些论文共有的论证顺序

### 摘要

常见顺序是：

```text
任务及其决策瓶颈
→ 现有方法在该瓶颈上的具体失效
→ 一个可复述的核心机制
→ 该机制为什么直接缓解失效
→ 数据集、强基线和定量结果
```

摘要很少罗列全部模块，也不会把“代码能输出 CSV、置信区间”当成算法贡献。尚无正式结果时，正确做法是保留结果位置并降低主张，而不是用实验计划代替结果。

### 引言

录用论文通常在第一页完成四件事：

1. 用具体决策对象定义问题，而不是先讲宽泛行业背景；
2. 把难点拆成两到三个可观察的技术失效；
3. 说明新方法的每个模块分别解决哪个失效；
4. 贡献列表写“提出了什么并由什么证据验证”，而不是罗列仓库功能。

例如，AAAI-23 retrospective branching 先明确长轨迹、大动作空间和部分可观测三个困难，再逐项解释 retrospective trajectory 如何缩短轨迹、降低方差并改善可预测性。这种一一映射比“我们提出一个新框架，具有更强泛化性”更可信。

### 方法

方法部分先给执行顺序，再给公式。每个小节通常有三层：

1. 输入和输出是什么；
2. 实际执行哪些步骤；
3. 为什么这些步骤针对前文的困难。

AAAI-24 cutting-plane 论文会直接写清替代模块在何时调用、何时仍调用精确主问题以及如何保留最优性；AAAI-22 调度论文则把可行性恢复作为模型的一部分，而不是一句“保证可行”。本稿因此必须明确：策略从 SCIP 已生成的候选 cut 中选择，未被选择的 cut 如何处理，以及为什么不会改变可行域。

### 实验

较强的论文会先声明要验证的命题，再列数据、基线和指标。常见证据链是：

```text
主结果 → 机制消融 → 跨规模/跨类型 → 开销或失败案例
```

此外，作者会主动限定比较范围。AAAI-23 retrospective branching 明确说明其阶段性工作不与调优后的商业求解器竞争。这种边界声明不会削弱论文，反而避免审稿人发现夸大。

## 3. 语言层面的共同特征

- 段首直接给本段判断，后续句子只解释该判断。
- 优先使用可核验名词，如“single-slot aligner”“candidate-cut cardinality”“primal-dual integral”，少用“powerful framework”“comprehensive infrastructure”。
- “However”后面跟具体缺陷及其后果，不跟抽象的“仍存在挑战”。
- 方法句使用动作顺序：represent、compute、select、rerank、return。
- 结果句必须包含比较对象、数据范围、指标和数值。
- 限定词使用自然：在证据不足时写“we study”“we test”“we do not claim”，不写“universally improves”。

## 4. 原稿的主要问题

1. **两条主线抢叙事中心。** 双源旋转腔 MILP 与通用 cut selection 都被写成第一贡献，读者无法判断论文究竟解决调度建模还是学习求解。
2. **方法动机过于抽象。** 原稿说通用特征“看不到物理块”，但新版特征其实按 SCIP 变量角色划分，与 route、4x1、2x2 名称无关。
3. **实验计划被写成贡献。** “输出 raw records、置信区间、提供 infrastructure”是复现要求，不是科研结论。
4. **过多元话语。** “present draft”“final study”“remaining step”属于项目管理语言，不属于投稿正文。
5. **缺少机制级定义。** 角色配额、相似度惩罚、checkpoint 语义版本和并行采样方式没有得到与代码一致的解释。
6. **主张和证据不对齐。** 当前只有 formulation validation 和 smoke test，不能在摘要中暗示优于 SCIP、ACS 或 HEM。

## 5. 新稿采用的单一故事线

新稿以“学习辅助 MILP 求解”为主线，以双源旋转腔调度作为提出问题并检验方法的困难应用：

```text
双源混流调度产生离散批次—连续时间强耦合 MILP
→ SCIP 在一个分离轮次产生大量作用角色不同的 cuts
→ 仅凭 13 个通用质量量度，层次策略容易集中选择相似 cuts
→ 用变量角色系数质量描述 cut 的离散—连续作用结构
→ 高层决定数量、pointer 给出顺序、角色配额与相似度惩罚修复冗余
→ 在 Petri 未见规模和通用 MILP/MIPLIB 上分别验证效果与边界
```

调度 MILP 保留为独立技术贡献，但只描述真正实现的物理语义：AL 单槽串行校准、ATR/VTR 满载与空载移动、上下 LL 容量、4x1 旋转批次、2x2 交换链、PEC token 复用以及纯 PEC 清洁批次。

## 6. 改写硬规则

- 不把集中式轨迹聚合写成严格 A3C；统一称为 parallel actor--critic training 或 A3C-inspired training。
- 不把 ACS-Tuned 写成完整 Adaptive Cut Selection；只有存在 held-out instance predictions 时才称 full ACS。
- 不使用旧的 Petri 变量名前缀特征叙述。
- 不把 quick-demo 数字写入主结果。
- 在正式多种子结果完成前，不写任何优于基线的句子。
- 正式结果必须同时报告 PDI、时间、gap、节点、可行率、最优率和 callback 开销。
