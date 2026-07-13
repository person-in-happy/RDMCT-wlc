# AAAI-27 重写提纲、逆向提纲与主张—证据表

## 一、六点主线提纲

1. **任务：** 双源产品/PEC 晶圆在旋转式组合设备中共享 ATR、VTR、LL 和 CH，并混合执行 `4×1` 与 `2×2` 工艺。
2. **建模难点：** 可行调度必须显式处理 AL 单槽、机械手空载回位、LL 槽位、PEC token、换片链和纯 PEC 清洁。
3. **求解难点：** 模型把离散批次决策与连续时间析取资源约束耦合起来，混流规模增加后搜索迅速变难。
4. **方法缺口：** 13 个通用 cut 质量特征没有直接描述候选割的离散—连续变量角色结构，pointer 前缀可能结构重复。
5. **本文方法：** 10 个通用变量角色特征 + 高层预算 + pointer 顺序 + 策略锚定的角色子模补全。
6. **证据：** 当前只有调度模型验证；正式算法结论必须等待 HEM 与新 23D 模型的冻结多种子结果。

## 二、各节逆向提纲

| 章节 | 段落作用 | 本段核心句/信息 |
| --- | --- | --- |
| Abstract | task | 两个物料源和两种工艺共享有限设备资源 |
| Abstract | challenge | 通用 cut 特征不能区分不同离散—连续支撑结构 |
| Abstract | method | 变量角色系数质量 + 层次选择 + 单调子模补全 |
| Abstract | boundary | 只选择 SCIP 有效割；算法主结果仍在运行 |
| Introduction P1 | opening | 可执行调度需要逐晶圆、逐机械手、逐槽位决策 |
| Introduction P2 | domain gap | 现有组合设备研究没有覆盖本文全部物理组合 |
| Introduction P3 | solver gap | 细粒度 MIP 难解，已有 learned cut 特征缺少变量角色 |
| Introduction P4 | method | 三个模块分别补结构信息、数量/顺序和冗余问题 |
| Introduction P5 | contributions | 建模、表示、带近似保证的子模选择三项贡献，不把实验脚本列为贡献 |
| Related Work | positioning | 分别定位组合设备调度、learning for exact optimization、cut selection |
| Scheduling Model | model | 从路径、工艺、资源冲突、可行性细节到目标依次展开 |
| Cut Selection | method | 输入候选 cuts，依次提特征、选预算、排序、子模补全、返回 SCIP |
| Experimental Protocol | evidence design | 主结果、消融、泛化、开销一一对应三项方法主张 |
| Current Validation | evidence boundary | 只陈述已有模型结果，并明确算法结果未完成 |
| Limitations | scope | 角色较粗、子模权重待消融、无生产数据、并非严格 A3C |

## 三、主张—证据表

| 主张 | 代码或实验依据 | 状态 |
| --- | --- | --- |
| 模型显式表示双源物料路径 | `petri_mip_generator.py` 中产品/PEC stage 与路径约束 | supported |
| AL 中两片晶圆串行校准 | `al_exchange_time`、companion place 和 AL 一元资源约束 | supported |
| ATR/VTR 包含空载回位 | endpoint-dependent transition time 与 action chain | supported |
| PEC 不能重叠复用 | `pec_token_assign_*` 及 token occupation interval | supported |
| 清洁是纯 PEC 旋转批次 | `clean_active_*`、clean load/process/unload 和 epoch 约束 | supported |
| 23D 表示不读取变量名 | `utils.py::_extract_structure_profile()` 只读取 SCIP 元数据 | supported |
| HEM 严格使用 13D | 独立 generic extractor 与 checkpoint 输入维数检查 | supported |
| 子模补全保持 cut 数量且不改不等式 | `_apply_structure_aware_selection()` 只返回 SCIP 已生成 cut 的索引前缀 | supported |
| 固定策略锚点后贪心补全具有 $(1-1/e)$ 残余保证 | 非负 modular + concave-over-modular role coverage + facility-location 均为单调子模函数 | supported（正文含证明要点，附录仍应补完整证明） |
| 方法属于并行层次策略梯度 | 多 SCIP 进程采样后集中执行 REINFORCE 更新 | supported |
| 方法是严格 A3C | 梯度不是异步更新 | false，正文已删除该主张 |
| 方法优于 SCIP / ACS / HEM | 正式多种子结果未完成 | needs evidence |
| 方法跨规模泛化 | 数据切分和 runner 已实现，尚无冻结结果 | needs evidence |
| 方法跨 MIP family 泛化 | 四类生成器与 MIPLIB 接口已实现，尚无冻结结果 | needs evidence |

## 四、提交前审查

- **清晰性：** 当前主线只有一个；通过。
- **术语一致性：** 调度模型含可选凸二次等待约束，统一称 MIP；通过。
- **算法命名：** 使用 parallel hierarchical policy gradient，不写 strict A3C；通过。
- **无依据主张：** 摘要和结论均未声称算法胜过基线；通过。
- **缺失证据：** 主结果、消融、跨规模、跨类型、callback 开销仍缺；投稿阻塞项。
- **结果时效：** 当前 formulation 表需要用最终代码版本重新跑一遍再投稿；投稿阻塞项。
