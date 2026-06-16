# 双源混流半导体组合设备全流程 MIP 说明

本文档对应当前 `petri_mip_generator.py` 的最终版建模语义。该版本不再把 `4x1` 简化成“一个抽象槽位”，而是按设备资料显式区分旋转腔中两组可达槽位，并保持产品 wafer 与 PEC wafer 的端到端全路径调度。

## 1. 建模对象

设备资源包括：

- `LP1`-`LP4`：每个 `25` 槽位
- `ATR`：大气机械手
- `AL`：单槽位校准器
- `LLupper`：上层真空锁，`2` 槽位
- `LLlower`：下层真空锁，`2` 槽位
- `VTR`：真空机械手
- `CH2`、`CH3`：两个共享四槽位旋转腔
- `PEC storage`：`10` 槽位，默认 `8` 片可循环 PEC wafer

产品 wafer 路径：

`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`

PEC wafer 路径：

`PEC storage -> VTR -> CH -> VTR -> PEC storage`

## 2. 输入与 PW 对

输入可以通过两种方式给出：

1. `full_mode_wafers` 与 `mix_mode_wafers`
2. wafer 级 `mode_sequence`

同模式产品 wafer 每两片构成一个 PW 对：

- 偶数尾：`product + product`
- 奇数尾：最后一个 PW 对自动变为 `product + PEC`

因此，旋转腔真空侧的基本装载单元不是单片 wafer，而是“2 片 wafer 的 PW 对”。

## 3. `4x1` 的最终正确语义

### 3.1 物理规则

根据设备说明，四槽位旋转腔只有靠近 `VTR` 的两槽可直接取放。对 `4x1` 来说，一个满腔批次的真实顺序是：

1. 前侧两槽装入 1 个 PW 对
2. 腔体自转 `180°`
3. 后侧两槽装入 1 个 PW 对
4. 工艺加工 1 次
5. 先卸后侧两槽
6. 腔体再自转 `180°`
7. 再卸前侧两槽

这意味着 `4x1` 批次内部存在两个有先后顺序的物理 side-slot：

- `side 1`：先装后卸
- `side 2`：后装先卸

### 3.2 MIP 变量

当前代码中，`4x1` 相关的核心变量为：

- `assign_full_(p,m,b,s)`：PW 对 `p` 是否分配到 chamber `m` 的第 `b` 个 `4x1` 批次、以及该批次中的 side-slot `s`
- `full_batch_used_(m,b)`：该 `4x1` 批次是否被启用
- `full_filler_side_(m,b,s)`：该 side-slot 是否由 `PEC+PEC` 纯 PEC 对补满
- `full_batch_serial_order_(m,b,b+1)`：同一 chamber 的 `4x1` 批次按编号串行执行，后一批必须在前一批完全卸载后才能开始
- `full_batch_idle_(m,b,b+1,epoch)`：同一清洁 epoch 内相邻 `4x1` 批次之间的可避免空闲，用于二级目标压缩组间等待
- `full_to_mix_idle_(m,b,epoch)`：尾部 `4x1` 批次到同一 CH 后续 `2x2` 链之间的切换空闲
- 技术交底书要求同一 chamber 上 `4x1` 在 `2x2` 之前完成，因此代码不再包含旧版“2x2之后再追加4x1”的尾段变量

### 3.3 核心约束

对每个启用的 `4x1` 批次 `(m,b)`：

- 两个 side-slot 都必须被占满
- 每个 side-slot 恰好放 1 个 PW 对或 1 个纯 PEC 对
- 至少有 1 个 side-slot 承载产品 PW 对，禁止“两个 side-slot 都是纯 PEC”的空转批次
- 若只分到 1 个产品 PW 对，则另一个 side-slot 自动被纯 PEC 对补满

这正对应图片中的“补 0 / 1 / 2 / 3 个”的物理含义，只不过在 MIP 中统一折叠为：

- 奇数尾片先形成 `product + PEC`
- 若该 chamber 的最后一个 `4x1` 批次只落到 1 个产品承载 PW 对，则另一侧补 `PEC + PEC`；非尾部批次必须承载两个产品 PW 对

### 3.4 时间建模

当前最终版对 `4x1` 建立了 5 段连续时间：

- `full_front_load`
- `full_back_load`
- `full_process`
- `full_back_unload`
- `full_front_unload`

并显式加入两次 `180°` 腔体自转时间：

- `front_load -> back_load`
- `back_unload -> front_unload`

因此，产品 PW 对在 `4x1` 中的 `vtr_load` / `pm` / `vtr_unload` 不再被错误地压成同一个公共装载段和公共卸载段，而是按所在 side-slot 继承不同的装卸时刻。

## 4. `2x2` 的最终语义

`2x2` 仍按设备资料建模为单腔连续链：

- 链首有 1 个纯 PEC 边界对
- 链尾有 1 个纯 PEC 边界对
- 中间是按位置顺推的产品 PW 对
- 每个产品 PW 对跨越两次相关 chamber 占用，符合“装入后经旋转再被卸出”的真实时序

对应变量为：

- `assign_mix_(p,m,r)`
- `mix_pos_used_(m,r)`
- `mix_cycle_used_(m,c)`
- `mix_last_cycle_(m,c)`
- `mix_last_pos_(m,r)`

对应的时间段为：

- `mix_head`
- `mix_cycle`
- `mix_bridge`
- `mix_tail_load`
- `mix_tail`

## 5. 产品 wafer 全路径阶段

每片产品 wafer 都建立以下阶段变量：

- `atr_lp_al`
- `al`
- `atr_al_llupper`
- `llupper`
- `vtr_load`
- `pm`
- `vtr_unload`
- `lllower`
- `atr_lllower_lp`

并定义：

- `wafer_completion_w = end(atr_lllower_lp)`
- `c_max = max_w wafer_completion_w`

目标函数为：

- `min c_max + lambda * (full_pm_imbalance + mix_pm_imbalance) + gamma * sum(chamber_idle_slack) + epsilon * sum(wafer_completion)`

主目标是最小化“第一片产品 wafer 离开 LP 到最后一片产品 wafer 回到 LP”的端到端总完工时间；`lambda` 为很小的软惩罚权重，用于鼓励 `4x1` 与 `2x2` 产品负载在 CH2/CH3 之间合理分担；`gamma` 用于压缩同一 CH 上相邻加工组之间的可避免空闲；`epsilon` 用于鼓励产品晶圆更早完成。`chamber_idle_slack` 包括 `full_batch_idle_*`、`full_to_mix_idle_*` 以及 `2x2` 链内部的 `mix_head_idle_*`、`mix_cycle_to_bridge_idle_*`、`mix_bridge_to_cycle_idle_*`、`mix_tail_idle_*`。这些 idle 项是软惩罚，不会在上游资源、PEC token 或 cleaning 未就绪时强行要求零等待。

## 6. PEC wafer 显式复用

PEC wafer 不再只作为数量预算存在，而是被建模为真实的可复用时序资源。当前显式覆盖了：

- 奇数尾片形成的 `product + PEC`
- `4x1` 中的 `PEC + PEC` 纯 PEC 补位对
- `2x2` 的头边界 PEC 对
- `2x2` 的尾边界 PEC 对

每个活动 PEC 作业都必须绑定到一个 `pec_token_assign`，从而把 PEC 数量约束转化为真实的时间区间不重叠约束。

## 7. CH 清洁作业

设备说明中的“累计加工若干次后必须执行 1 次 chamber 清洁作业”已经进入当前 MIP。代码默认使用 `cleaning_interval=10`，即同一 CH 的相邻两次清洁之间最多允许 10 次满腔加工；`cleaning_interval=0` 可用于显式关闭该约束。清洁时长默认取 `2 * full_process_time`，也可用 `cleaning_process_time` 直接指定。

清洁被建模为纯 PEC 的满腔批次：

- `clean_front_load`：VTR 装入前侧 2 片 PEC
- 腔体自转 `180°`
- `clean_back_load`：VTR 装入后侧 2 片 PEC
- `clean`：执行清洁加工
- `clean_back_unload`：先卸后侧 2 片 PEC
- 腔体自转 `180°`
- `clean_front_unload`：再卸前侧 2 片 PEC

清洁作业同时占用：

- 对应 CH 的完整窗口
- VTR 的四段装卸动作
- 4 个可复用 PEC token

模型用 `process_epoch_used`、`full_batch_epoch`、`mix_block_epoch`、`mix_cycle_epoch` 将同一 CH 的加工划分为清洁分隔的 epoch，并约束每个 epoch 内的满腔加工次数不超过 `cleaning_interval`。`2x2` 连续链保持在同一个 epoch 内；若单条 `2x2` 链超过清洁阈值，模型会通过分配到不同 CH 或报告不可行来避免违反清洁要求。

## 8. 显式资源约束

- `ATR`：所有 `LP->AL`、`AL->LLupper`、`LLlower->LP` 互斥
- `AL`：单槽位
- `LLupper`：双槽位
- `LLlower`：双槽位
- `VTR`：承担全部 `4x1` 前/后侧装卸、`2x2` 的链首/桥接/尾部操作，以及清洁装卸
- `CH2`、`CH3`：约束 `4x1` 批次窗口、`2x2` 连续块和清洁窗口互斥

## 9. 当前实现边界

当前最终版已经覆盖：

- 产品 wafer 与 PEC wafer 的完整往返路径
- `4x1` / `2x2` 的真实满腔与补片语义
- `4x1` 两组可达槽位的先装后卸约束
- `AL`、`LLupper`、`LLlower`、`ATR`、`VTR` 的显式容量与互斥
- PEC wafer 的时序复用
- 按累计满腔加工次数触发的 CH 清洁作业

当前 `2x2` 被保持为单腔连续链，清洁不会插入链内部。若未来需要支持单条超长 `2x2` 链中途清洁，应将 `2x2` 链拆成多个可由纯 PEC 清洁批次分隔的子链。
