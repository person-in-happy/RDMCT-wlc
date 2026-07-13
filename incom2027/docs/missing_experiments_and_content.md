# INCOM 2027：缺失实验与内容清单

当前初稿在格式和论文主线上完整，但科学证据还不能直接投稿。下面按“必须完成”“强烈建议”“投稿前填写”区分。

## 一、必须完成的实验

### 1. SPBS 的成对消融

需要回答：初解到底是否加快找到第一可行解、改善全程 primal-dual integral，而不是只证明能够加载。

固定同一实例、SCIP seed、时间上限和全部求解参数，对比：

- 无 warm start；
- SPBS full；
- SPBS relaxed（不固定 VTR 顺序）。

至少报告：初解构造时间、初解接受率、time to first incumbent、PDI、最终 gap、求解时间、节点数和最优率。当前 7,086 s 大实例只是一条可行性证据，不能写成性能提升。

### 2. 混流规模与配比实验

必须覆盖纯 $4\times1$、纯 $2\times2$、平衡混流和不平衡混流。建议测试：

- 训练规模：总产品数不超过 12；
- 验证规模：16；
- 测试规模：24、32，以及资源允许时的 48、64；
- 未见配比：`16+8`、`8+16`、`24+8`、`8+24`。

每个实例除求解指标外，还需报告 $C_{max}$、ATR/VTR/CH2/CH3 利用率、产品等待时间、PEC 使用峰值和清洁次数。这样 INCOM 论文才能把求解器收益落实到生产调度意义。

### 3. 割选择正式比较

至少比较：

- SCIP Default；
- ACS-Tuned；
- HEM 13D；
- 23D role feature-only；
- 23D role + submodular completion。

必须分别训练 HEM 与两个 23D 版本，禁止使用旧 23D checkpoint。当前特征 schema 应为 `universal_mip_role23_v2`，完整方法还应匹配当前 postprocessor schema。

正式统计建议使用 5 个训练 seed、至少 10 个 SCIP seed。按实例和 SCIP seed 配对，报告 bootstrap 95% CI、paired Wilcoxon 和 Holm 校正。只有原始 CSV 可追溯且统计门槛通过后，才能写“优于”“提升 x%”。

### 4. 结构消融

最小消融表：

| 版本 | 13D 通用特征 | 10D role 特征 | 分层预算 | submodular completion |
| --- | --- | --- | --- | --- |
| HEM | 是 | 否 | 是 | 否 |
| Role-only | 是 | 是 | 是 | 否 |
| Full | 是 | 是 | 是 | 是 |

还应单独关闭 submodular 目标中的质量、角色覆盖、facility-location 三部分，验证收益不是来自额外计算量或更大的候选池。

## 二、强烈建议的实验

### 5. 调度模型有效性与物理检查

为每种配方和清洁边界自动检查：

- AL 任意时刻最多一片；
- 不出现 `empty wafer`；
- 非清洁状态不允许纯 PEC 腔室生产批；
- VTR/ATR 连续 loaded moves 之间存在正确的空载回位；
- VTR waiting 只统计有载但无动作，idle 不作为 waiting；
- PEC token 占用区间不重叠；
- $2\times2$ 只有交换片需要的桥接等待较长。

建议将检查结果作为附录或补充材料，而不是仅凭甘特图人工判断。

### 6. 求解开销

分别报告 role feature 提取、神经网络推理、submodular completion 和 SPBS 构造时间。若 cut callback 节省的节点被 Python 回调开销抵消，单看节点数会产生误导。

### 7. 跨家族验证

INCOM 正文篇幅只有 6 页，跨 MILP 家族不是主表，但可用作“role 特征不依赖变量名”的补充证据。建议从 set cover、multidimensional knapsack、capacitated facility location、maximum-weight independent set 和 MIPLIB 2017 各选固定测试集，并按 family 报告，不要只给总平均。

## 三、可直接复用的现有入口

本目录 `reused_from_aaai/experiment_harness/` 已复制统一 benchmark、合并结果、ACS 调参脚本和 suite 配置。它们的文件名仍带 `aaai27`，以保留来源并避免误认为是新的独立实现。正式运行仍建议从仓库根目录使用已经调通的入口：

```powershell
.\aaai\run_aaai.ps1 -Stage check
.\aaai\run_aaai.ps1 -Stage generate-data
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds "1,2,3,4,5" -GpuDevice cuda:0
.\aaai\run_aaai.ps1 -Stage train-feature-only -Seeds "1,2,3,4,5" -GpuDevice cuda:0
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds "1,2,3,4,5" -GpuDevice cuda:0
.\aaai\run_aaai.ps1 -Stage tune-acs -TimeLimit 60
.\aaai\run_aaai.ps1 -Stage benchmark-all -Seeds "1,2,3,4,5,6,7,8,9,10" -TimeLimit 600 -GpuDevice cuda:0
```

运行前先核对 `run_aaai.ps1 -?` 的实际 stage 名称；如果现有入口使用 `train-proposed-submodular` 而不是 `train-proposed`，以脚本帮助为准。不要在训练尚未完成时用 quick-demo 结果填主表。

## 四、投稿前必须补齐的文字

- 作者、单位、通讯邮箱和基金；
- 设备参数来源：真实设备、工程给定还是合成参数；
- 计算硬件、操作系统、SCIP/PySCIPOpt/PyTorch 版本；
- 数据划分的实例数与随机生成规则；
- 最终表格及与摘要、引言、结论完全一致的数值；
- 失败案例：何种配比、清洁频率或 PEC 数量使 SPBS/selector 失效；
- 代码和数据发布方式；
- 最终 AI-assisted writing 声明和出版许可。

## 五、INCOM 取舍建议

6 页正文不适合同时展开全部 AAAI 算法细节。最终稿优先保留：设备问题、物理模型、SPBS、调度主表和 cut selector 的核心定义。通用 MILP/MIPLIB、全部超参数和大消融应放补充材料或后续期刊扩展。

