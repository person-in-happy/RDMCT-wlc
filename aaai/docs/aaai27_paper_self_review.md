# AAAI-27 重写稿自审

完整逆向提纲和逐项证据见 `aaai27_rewrite_outline_and_claim_map.md`。

## 五维审查

### 1. Contribution — `partial; method strengthened, evidence pending`

- 已明确为三项：细粒度双源旋转调度 MIP、通用变量角色 cut 表示、角色感知子集修复。
- 不再把日志、runner、CSV 或统计脚本写成科研贡献。
- 原固定配额与余弦惩罚已替换为策略锚定的单调子模补全目标。质量、凹角色覆盖和 facility-location 代表性具有统一边际增益解释；固定锚点后的贪心补全具有标准 $(1-1/e)$ 残余近似保证。
- 该修改降低了“启发式工程拼装”风险，但仍必须用 feature-only、子模组件和跨 family 消融证明净价值。

### 2. Writing clarity — `pass for draft`

- 引言采用“设备决策 → 模型困难 → cut 表示缺口 → 对应方法”的单线结构。
- 方法给出了 10 个新增特征、基本分数、角色配额和相似度惩罚的具体定义。
- 术语已纠偏：模型称 MIP；训练称 parallel hierarchical policy gradient；不宣称 strict A3C。

### 3. Experimental strength — `needs new experiment`

- 当前只有 formulation validation，不能声称优于 SCIP、ACS 或 HEM。
- 投稿前需要 5 个训练 seed、至少 10 个 SCIP seed，以及 Petri、四类 MIP 和 MIPLIB 冻结结果。

### 4. Evaluation completeness — `needs new experiment`

- 必须补 HEM 13D、23D feature-only、23D full submodular 三组主消融。
- 正式 runner 已加入配对 Wilcoxon、Holm 校正和 claim-ready 门槛；结果尚未产生。
- 必须报告 PDI、runtime、gap、nodes、incumbent/optimal rate 和 callback 开销。
- ACS-Tuned 与 full ACS 必须保持名称区分。

### 5. Method design soundness — `partial`

- 优点：不修改 SCIP cuts；特征不依赖变量名；checkpoint schema 防止语义错配。
- 风险：五类变量角色较粗；子模分量权重、扩展池倍率和锚点比例固定；未利用约束图和 cut provenance。
- 必须报告跨 family 失败案例，不能只给总平均。

## 当前投稿判定

英文稿已同步子模方法和近似保证，但尚未达到可提交状态。旧 23D checkpoint 的 rollout 后处理语义不兼容，必须用 `role_submodular_v1` 重新训练；主结果、五训练种子、十 SCIP 种子和跨 family 结果仍是投稿阻塞项。
