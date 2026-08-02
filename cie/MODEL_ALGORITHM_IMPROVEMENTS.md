# CIE 模型与算法改进说明

本项目的改进遵循两个边界：模型压缩不得删除原问题的可行解；算法增强不得通过弱化基线、改变时限或隐藏失败样本来制造优势。

## 严格等价的模型压缩

- 对已经由等式固定为 0/1 的成员关系、槽位分配和腔室别名变量，保留原变量名以兼容 warm start 与甘特图，但把变量类型从二进制改为 `[0,1]` 连续变量。等式仍强制其取 0/1，因此最优解和可行域不变。
- 当一个任务必须占用全部允许槽位时，槽位分配变量同样可连续化；存在真实槽位选择时仍保留二进制变量。
- 2x2 的 `PEC+P1, P1+P2, ..., Pk+PEC` 链、4x1 批处理、提前清洁、清洁后 PEC 驻留、共享机械手与装载锁等物理语义均不得因压缩而删除。
- 后续优先用匿名库存/事件流表示 8 片同质 PEC，避免按 PEC 身份建立 `O(J^2K)` 排序变量；该重构必须先通过小规模逐解对照验证，才能替换现有精确模型。

## 优化目标

主目标优先最小化完工期 `Cmax`。在相同 `Cmax` 下，再最小化五类物理资源总空闲时间的平方和，并用可避免等待的线性和打破同值。若资源 `r` 的容量为 `c_r`、固定工作量为 `W_r`，则 `I_r = c_r * Cmax - W_r`，紧凑二级目标为 `sum_r I_r^2 + sum_g wait_g`。

在工作量固定、资源状态只有工作或空闲时，总 idle 平方确实包含缩短总时间的效果，而且固定 `Cmax` 后它基本为常数；此时真正区分同完工期甘特图的是线性等待项。仍保留 `Cmax` 为第一层目标，是为了覆盖可选清洁、不同搬运方案等会改变工作量的情形，避免模型通过增加工作量来虚假减少 idle。旧的逐等待平方目标仍可通过 `legacy_wait_square` 复现。若第二阶段固定离散决策，它属于 incumbent 精修，不宣称全局二级最优。

## A3C 目标对齐

- 训练奖励、命令行默认值与 checkpoint 选择指标统一到 primal-dual integral（PDI）；PDI 越小越好。
- 学习策略只对 SCIP 已生成的合法割排序/选取，不生成未经验证的约束，也不直接剪枝，因此不改变精确求解的最优性保证。
- beam search 统一累计 log-probability，按 backpointer 同步重排 hidden/cell/mask，并从最终束回溯完整序列；带 token 策略在首个 EOS 截断。旧 beam 结果因实现错误不得与修复后结果拼表。
- 正式消融必须显式指定 learned selector 为 `on` 或 `off`；`auto` 仅用于部署稳健性实验，不能在困难实例上静默退化后仍记作完整 A3C。
- learned 与 heuristic beam 统一采用“便宜 efficacy 预筛、再提取完整特征”的候选上限；未选 cuts 仍全部按合法排列返回 SCIP。
- 所有算法臂共享相同模型、warm start、线程数、随机种子和 SCIP 时限。SCIP wall clock 包含 callback、网络推理和 beam 搜索；raw/汇总表另报从 env reset 到结果写出的端到端时间及 feature/transfer/policy/rerank 分项，预生成 warm start 必须对所有臂共享。

## 公平消融与报告指标

模型消融依次比较 Legacy、严格等价 Compact、Compact+局部 Big-M、Compact+有效不等式；算法消融在同一模型上比较 SCIP、heuristic beam、A3C top-k、A3C+beam、自适应选割、置信度回退。

至少报告最终 primal/dual/gap、PDI、primal integral、首次可行解时间、最佳解时间、证明时间、根节点 gap closed、节点数、LP 迭代数、割数量、推理/beam 开销和 proven-optimal 比例。所有实例与种子配对统计，不删除失败或超时样本。

迁移保留的 ACS 权重来自旧的混合验证集，只能作为启动值；正式 CIE 表格前必须仅在冻结的 `cie_validation` 上重新调参并锁定，不能接触 core/OOD 测试集。
