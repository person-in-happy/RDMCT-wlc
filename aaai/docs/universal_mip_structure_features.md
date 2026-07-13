# 通用 MIP 结构特征说明

## 一句话说明

本文方法的每个候选 cut 使用 23 个数表示：前 13 个是 HEM 使用的通用质量特征，后 10 个是与变量名和业务领域无关的结构特征。因此 Petri 调度、Set Cover、Knapsack、Facility Location、Independent Set、MIPLIB 和用户自己的 MIP 都调用同一个函数。

实现位置：`utils.py` 中的 `advanced_cut_feature_generator()` 和 `_extract_structure_profile()`。

## 23 个维度是什么

前 13 维保持不变：

1. objective parallelism；
2. efficacy；
3. support；
4. integral support；
5. normalized violation；
6–9. cut 系数的均值、最大值、最小值和标准差；
10–13. 目标系数的均值、最大值、最小值和标准差。

后 10 维全部按 cut 系数绝对值占比计算：

| 维度 | 名称 | 外行解释 |
| --- | --- | --- |
| 14 | binary decision mass | 这个 cut 有多大比例作用在 0/1 决策变量上 |
| 15 | general integer mass | 有多大比例作用在一般整数或隐式整数变量上 |
| 16 | objective-active continuous mass | 有多大比例作用在目标函数中系数非零的连续变量上 |
| 17 | continuous auxiliary mass | 有多大比例作用在目标系数为零的连续辅助变量上 |
| 18 | other mass | SCIP 元数据无法识别时的安全兜底比例 |
| 19 | finite-bounded mass | 有多大比例作用在上下界都有限的变量上 |
| 20 | positive coefficient mass | 正系数绝对值所占比例 |
| 21 | discrete–continuous coupling | cut 同时连接整数决策与连续变量的程度；两边均衡时最高 |
| 22 | dominant-role ratio | 最大变量角色占了多少，越大说明 cut 越集中 |
| 23 | normalized role entropy | 各角色是否分散，0 表示几乎只有一种角色 |

对于 cut $\sum_j a_jx_j\le b$，某个变量角色 $g$ 的质量占比为：

```text
该角色中所有 |a_j| 的和 / 所有变量 |a_j| 的和
```

这里不读取变量名字，也不检查名字前缀。

离散—连续耦合度定义为 `4 × 离散质量占比 × 连续质量占比`。只作用于离散变量或只作用于连续变量时它等于 0；两者各占约一半时接近 1。它替代了与正系数占比互补、信息重复的负系数占比。

## 为什么比旧版本更适合 AAAI

- **普适性：** 任意 MIP 都有变量类型、目标系数、上下界和 cut 系数。
- **无人工标签泄漏：** 测试集不需要告诉算法哪个变量属于哪个业务模块。
- **变量重命名不变：** 把 `x_1` 改成 `wafer_route_1` 不会改变特征。
- **可做跨域实验：** Petri 训练后的同一 checkpoint 可以原样测试四类生成 MILP 与 MIPLIB，泛化成败都可被公平测量。
- **可审计：** 每个维度有明确数学含义，可以单独消融并统计提取开销。

## checkpoint 兼容性

新 23D checkpoint 内必须有：

```text
cut_feature_schema = universal_mip_role23_v2
cut_postprocessor_schema = role_submodular_v1
```

旧模型虽然也是 23 维，但第 14–23 维含义不同，不能混用。加载器会主动报错，避免得到表面能运行、实际无效的实验结果。13D HEM checkpoint 没有改变。

## 投稿实验中必须补的证据

1. HEM 13D、23D 仅加角色特征、23D 加角色特征与子模补全三组消融；
2. Petri 未见规模和未见配比；
3. 四类生成 MILP 分 family 报告；
4. MIPLIB 单独报告，不把失败隐藏在总平均中；
5. 特征提取时间、网络推理时间和总 wall-clock 收益；
6. 至少 5 个训练 seed 和 10 个 SCIP seed，使用配对统计与置信区间。
