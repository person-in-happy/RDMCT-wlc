# CIRP CMS 2027：缺失实验与内容清单

CMS 审稿人更关注制造系统价值、设备真实性和可解释的性能改善。仅给求解器指标或通用 MILP 迁移实验不够。

## 一、必须完成的制造系统实验

### 1. 生产情景设计

至少构造以下因素的完整或正交实验：

- 配方比例：纯 $4\times1$、纯 $2\times2$、1:1、1:3、3:1；
- 批量：8、16、24、32，资源允许时增加 48/64；
- PEC 库存：从可行下界到设备上限；
- 清洁间隔：短、中、长；
- 腔室加工时间和 ATR/VTR 移动时间的低/标称/高水平；
- 两腔同质与适度异质情景。

主表报告 $C_{max}$、throughput、产品平均/95 分位 cycle time、ATR/VTR/各腔室利用率、PEC 峰值占用、清洁次数和求解 gap。

### 2. SPBS 对照

成对比较无初解、SPBS full、SPBS relaxed。每个情景使用相同实例和 SCIP seed，至少报告：

- 初解构造时间；
- 初解被原模型接受的比例；
- time to first feasible schedule；
- 60/300/600 s 时的 incumbent makespan 和 gap；
- PDI、节点数和最优率。

必须把初解时间算入总时间，避免只报告求解器读取初解后的时间。

### 3. 制造基线

至少增加一种不依赖学习的制造调度基线，例如：

- recipe-first/earliest-available dispatch；
- 先完成全部 $4\times1$ 再切换 $2\times2$；
- 固定 chamber allocation；
- rolling-horizon MIP；
- 简化分解或 priority rule。

SCIP Default 只是求解器基线，不能替代制造调度基线。

### 4. 甘特图物理一致性验证

将现有人工检查写成自动验证器或至少形成逐实例审计报告：

- AL 单槽且两片串行校准；
- 单片尾批由 LP 单取，缺口使用真实 PEC；
- 纯 PEC 腔室只在清洁相关状态出现；
- ATR/VTR loaded move 前后位置连续，缺少回位即失败；
- robot waiting 与 idle 分开；
- PEC token 区间不重叠；
- $2\times2$ 的桥接等待只发生在交换语义要求的位置；
- LL 每层每槽不重叠。

正文至少展示一个 $4\times1$、一个 $2\times2$ 和一个含清洁的混流 Gantt，图下注明验证器通过。

## 二、强烈建议的证据

### 5. 与工业数据的连接

最好使用匿名真实参数：设备 travel/pick/place/align/process/clean 时间、PEC 上限、lot size 和配方比例。如果无法取得，应说明参数来自工程设计值，并给出足够宽的敏感性范围。不要把合成实例写成生产线实测。

### 6. 结构贡献消融

依次关闭或聚合以下细节，观察是否产生不可执行计划或过于乐观的 makespan：

- 忽略空载回位；
- 把 AL 当双槽；
- 允许 fictitious empty wafer；
- 不跟踪 PEC token；
- 清洁必须等待整个 $2\times2$ 链完成。

这组实验能直接说明详细模型为何对制造系统有必要，比通用 MIPLIB 实验更适合 CMS。

### 7. 可扩展性和运行时间

报告变量/约束数量随 wafer 数、候选 batch 数和清洁段数增长的曲线。给出内存峰值、求解时间、gap，以及何时需要 rolling horizon 或分解。

## 三、当前可复用与不建议复用的 AAAI 内容

已复制到 `reused_from_aaai/`：原英文稿、参考文献、流程图。CMS 初稿实际复用了设备描述、模型定义、SPBS 和四条验证记录。

不建议在 CMS 主文复用：

- 通用 23D cut feature 的完整推导；
- set cover/knapsack/facility location/independent set/MIPLIB 主表；
- AAAI 多 seed 训练叙事。

这些内容会削弱制造系统主线。若后续正式结果表明 cut selector 显著改善大规模调度，可把它作为求解增强的一小节和一个消融，而不是论文标题贡献。

## 四、投稿前内容缺口

- 作者、单位、通讯作者信息；
- 摘要系统的字数和必填字段；
- 2027 最终页数限制；
- 参数来源和实验硬件；
- 至少一个自动验证通过的可读 Gantt；
- 主实验及置信区间；
- 工业意义：每小时吞吐、设备利用率或预计节拍改善；
- 局限性与失败案例；
- 数据/代码可用性声明；
- 利益冲突、基金、AI-assisted writing 和 Procedia license 信息。

## 五、与 INCOM 的关系

本目录是第二选择，不是并行重复投稿包。若 INCOM 已经投稿且仍在审，不应提交本稿全文。若未来把两项工作拆开，建议 INCOM 只保留通用 cut selection 和跨 MILP 泛化，CMS 只保留设备模型、物理验证和生产实验，并在两文中互相引用、明确新增贡献。

