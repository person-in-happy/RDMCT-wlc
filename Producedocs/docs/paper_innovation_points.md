# Paper Innovation Points

## English

This work studies a dual-source mixed-flow semiconductor cluster scheduling problem with shared rotary chambers `CH2` and `CH3`. The corrected MIP differs from the earlier pair-level abstraction in one important way: the input is now given as arbitrary counts of `4x1` and `2x2` product wafers, and the MIP itself performs wafer-to-PW-pair formation before chamber scheduling.

The main innovations are:

1. We formulate a wafer-driven exact MIP for the dual-source mixed-flow rotary-chamber scheduling problem. Product wafers are first assigned to mode-consistent PW pairs, and odd residual wafers are completed by PEC wafers inside the MIP.
2. The model captures both pair-formation PEC usage and chamber-level PEC usage in a unified budget, including odd-tail `product + PEC` PW pairs, `4x1` pure-PEC supplementation pairs, and `2x2` boundary PEC pairs.
3. The scheduling layer still preserves the exact shared-chamber semantics of `4x1` slots, `2x2` ordered sequences, mode non-overlap, and makespan minimization over product wafer completion times.
4. On top of the corrected MIP, the learning-to-cut framework uses structure-aware cut features and family-aware post-selection to better cover pair-formation, chamber-assignment, timing, and completion bottlenecks.

## 中文

本文关注共享旋转腔 `CH2 / CH3` 上的双源混流半导体组合设备调度问题。修正后的 MIP 不再把“产品对”作为外部已知输入，而是从任意数量的 `4x1` 与 `2x2` 产品 wafer 出发，在模型内部先形成 PW 对，再进行共享腔调度。

本文的主要创新点包括：

1. 建立了一个 wafer 驱动的精确 MIP。模型首先把产品 wafer 分配到同模式 PW 对中，并在奇数尾对时自动引入 `product + PEC` 补位。
2. 在同一个 PEC 预算中统一刻画三类 PEC 消耗：奇数尾对内部补位、`4x1` 槽位级纯 PEC PW 对补足、以及 `2x2` 首尾边界纯 PEC PW 对。
3. 在保持共享旋转腔 `4x1 / 2x2` 工艺语义精确性的同时，将目标从旧的 pair 完工时间自然提升到产品 wafer 完工时间层面。
4. 在修正后的 MIP 基础上，继续引入结构感知 cut 表征和 family-aware 的重排机制，使学习式 cut selection 更好覆盖配对、分配、时序和完工相关瓶颈。
