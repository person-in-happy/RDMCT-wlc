# 四槽 PM 4x1 组合设备调度问题描述与建模提示

本文档根据以下两篇本地文献整理：

- `E:\work\1\毕设\文献\四腔MIP-ieee.pdf`：会议版，给出 `BS` 与 `HTS` 两类稳态调度策略及两个线性规划。
- `E:\work\1\毕设\文献\四腔MIP.pdf`：期刊扩展版，给出 `OBS`、`OHTS`、`TBS`、`THTS` 四类稳态调度策略及四个线性规划。

文献模型的本质是：先固定周期性 robot task sequence，再把调度问题转化为连续时间 LP。若把“从多个策略中选择最优策略”也放进同一个模型，可以用二进制变量包装成一个 MIP；否则每个策略本身是一个 LP。

## 1. 设备说明

文献研究的设备是带四槽工艺腔和四指机械手的组合设备，文献中称为 `SF3-CT`。设备由若干个四槽 process module、一个双臂双指 robot 和若干 loadlock 组成。

主要部件如下：

- `PM`：每个工艺腔有 `4` 个 wafer space。任一时刻只有靠近门口的 `2` 个 space 能被 robot 直接取放，另外 `2` 个 space 在相对侧；腔体内部可以旋转，使另一组 space 转到门口。
- `Robot`：双臂，每个臂有 `2` 个 finger，一次可以搬运 `2` 片 wafer。两个臂结构上耦合，不能完全独立并行操作。
- `Dirty arm`：只搬运未加工或脏 wafer，负责从 loadlock 取出原片并送入第 `1` 道工艺。
- `Clean arm`：搬运已完成第 `1` 道工艺后的 clean wafer，负责后续工艺步之间转运，并把成品送回 loadlock。
- `LL`：loadlock 存储原片和成品。文献把原片 LL 视为 step `0`，成品 LL 视为 step `n+1`，通常假设 LL 供应充足，不是吞吐瓶颈。

文献中的 wafer flow pattern 写作：

```text
WFP = (m1, m2, ..., mn)
```

其中 `n` 是工艺步数，`mi` 是第 `i` 道工艺可用的并行 PM 数量。

## 2. 4x1 满腔过程

文献语境下的 `4x1` 可以理解为：一个 PM 满腔时同时处理 `4` 片同一道工艺的 wafer；由于 robot 每次用一个双指臂搬 `2` 片，满腔由两个 `2` 片 wafer pair 构成。

对第 `i` 道工艺，文献把先装入的两片记为 `W_i,12`，后装入的两片记为 `W_i,34`。一个满腔周期的物理过程为：

1. Robot 把 `W_i,12` 装入 PM 门口的两个 space。
2. PM 内部腔体旋转，使另外两个空 space 面向门口。
3. Robot 把 `W_i,34` 装入 PM。
4. PM 再旋转，使 `W_i,12` 回到门口侧。
5. 四片 wafer 同时加工。
6. 加工结束后先卸 `W_i,12`。
7. PM 再旋转。
8. 再卸 `W_i,34`。

因此文献采用的是 `FIFO` 语义：先装入的 `W_i,12` 也先卸出。若把该文献方法迁移到当前仓库的端到端全流程 MIP，需要特别注意：当前仓库文档中 `4x1` 侧位语义按具体设备资料实现，可能采用“先装后卸 / 后装先卸”的 side-slot 关系；迁移时必须以目标设备真实动作顺序为准。

## 3. 问题描述

给定以下输入：

- 工艺步数 `n` 和 wafer flow pattern `(m1, ..., mn)`。
- 每道工艺的 PM 加工时间 `alpha_i`。
- 每道工艺的 residency time 上限 `delta_i`。
- Robot 在普通 PM 上的装片/卸片时间。
- Robot 在 LL 取原片时的时间，该时间包含对齐动作，通常比普通装卸更长。
- Robot 在两个模块之间移动或自身换臂旋转的时间。
- PM 内部腔体旋转时间 `upsilon`。
- 选择的周期性 robot task sequence。

要求确定稳态周期调度，使得：

- 每个启用的 PM 在稳态下尽量满腔加工 `4` 片 wafer。
- Dirty finger 与 clean finger 的用途不交叉，避免污染。
- 每片 wafer 在 PM 加工完成后必须在 `delta_i` 内被取出。
- 所有工艺步在稳态周期中完成相同吞吐量。
- 目标是最小化 robot cycle time，也就是系统 cycle time，从而最大化吞吐率。

文献不是直接搜索任意离散序列，而是先枚举少数具有物理意义的周期策略，然后对每个策略建立 LP 并求解。给定参数后，分别求解所有策略，选择可行且 cycle time 最小的方案。

## 4. 文献策略

会议版给出两个策略：

- `BS`：backward sequence。Clean arm 从末道工艺向前倒序搬运 clean wafer，dirty arm 再向第 `1` 道工艺补入 raw wafer。
- `HTS`：hybrid task sequence。在靠近第 `1` 道工艺的位置引入 swap 操作，其余部分仍保留 backward 思想。

期刊版扩展为四个策略：

- `OBS`：one-time backward sequence。一次完整 backward 周期完成四片 wafer 的推进。
- `OHTS`：one-time hybrid task sequence。在 `OBS` 基础上对前端工艺使用 hybrid/swap。
- `TBS`：two-time backward sequence。把一次四片推进拆成两次两片推进，重复两次形成一个四片生产周期。
- `THTS`：two-time hybrid task sequence。把 `OHTS` 的思想拆成两次两片推进。

策略固定后，robot 的任务顺序已知；剩下要优化的是各处等待时间，尤其是 robot 到达 PM 后等待加工完成或等待 PM 内部旋转完成的时间。

## 5. 建模方法总结

文献的建模流程可以概括为六步。

1. 固定策略。
   对 `BS/HTS` 或 `OBS/OHTS/TBS/THTS` 中的一个策略，先写出完整周期内的 robot 操作序列，包括 `U_i`、`L_i`、模块间移动、swap、PM 内部旋转和等待活动。

2. 定义连续变量。
   常用变量如下：

   | 变量 | 含义 |
   | --- | --- |
   | `psi_s` | 策略 `s` 下的 robot/system cycle time |
   | `theta_i` | 第 `i` 道工艺完成四片 wafer 所需的稳态时间 |
   | `omega_i1` | robot 到达 PM 准备卸 `W_i,12` 时，为等待加工完成产生的等待时间 |
   | `omega_i2` | 卸完 `W_i,12` 后，为等待 PM 旋转到 `W_i,34` 可卸位置产生的等待时间 |
   | `omega_i3` | 装完 `W_i,12` 后，为等待 PM 旋转到空位可装 `W_i,34` 产生的等待时间 |
   | `d_i` | 第 `i` 道工艺加工结束到 wafer 被抓取卸出的 delay |
   | `tau_i,12` | `W_i,12` 在第 `i` 道 PM 内的 sojourn time |
   | `tau_i,34` | `W_i,34` 在第 `i` 道 PM 内的 sojourn time |

3. 建立 RTC 约束。

   ```text
   alpha_i <= tau_i,12 <= alpha_i + delta_i
   alpha_i <= tau_i,34 <= alpha_i + delta_i
   ```

   这保证两组 wafer 都在允许驻留窗口内离开 PM。

4. 建立等待时间约束。
   `omega_i2` 和 `omega_i3` 由 PM 旋转时间与 robot 在此期间执行的任务长度共同决定，形式上是：

   ```text
   omega = max(PM_rotation_time - robot_tasks_during_rotation, 0)
   ```

   在线性模型中可写为：

   ```text
   omega >= PM_rotation_time - robot_tasks_during_rotation
   omega >= 0
   ```

   因目标最小化 `psi_s`，这些等待变量会被压到最小可行值。

5. 建立时间平衡约束。
   对每个策略，根据已固定的任务序列推导：

   ```text
   theta_i = (alpha_i + d_i + 固定robot任务时间 + 固定PM旋转时间 + 相关等待时间之和) / m_i
   psi_s = 固定robot周期任务时间 + 周期内所有等待时间之和
   psi_s = theta_i, for every process step i
   ```

   最后一组等式表达稳态平衡：每道工艺完成四片 wafer 的节拍必须等于 robot 周期节拍。

6. 最小化 cycle time。

   ```text
   minimize psi_s
   ```

   每个策略独立求解后，选取可行且 `psi_s` 最小的策略。若要形成单一 MIP，可增加二进制变量 `y_s` 表示是否选择策略 `s`，约束 `sum_s y_s = 1`，并用大 M 激活对应策略的约束。

## 6. 与当前仓库 MIP 的关系

文献模型和当前仓库 `petri_mip_generator.py` 的目标相近，但粒度不同：

- 文献模型是稳态周期 LP：默认 wafer 源源不断进入系统，策略预先固定，主要优化等待时间和 cycle time。
- 当前仓库模型是有限批端到端 MIP：显式调度产品 wafer 与 PEC wafer 的完整路径，包含 `LP/ATR/AL/LLupper/VTR/CH/LLlower`、PEC 复用、cleaning、CH2/CH3 负载平衡和甘特图所需时间段。
- 文献模型把 LL 抽象为 step `0` 和 `n+1`，不显式建模本仓库中的 `AL`、上下层 LL、PEC storage 和清洁批次。
- 文献 `4x1` 满腔按 FIFO 卸载；当前仓库应以设备资料定义的 `4x1` side-slot 顺序为准。

因此，若目标是复现文献，应生成“固定策略的稳态 LP/MIP”。若目标是生成当前项目可训练、可求解的 `.lp` 实例，应使用仓库的 `petri_mip_generator.py`。

## 7. 可直接给 AI 的建模命令

把下面整段作为提示词发给 AI，可以让它生成文献型稳态 LP/MIP 代码。

```text
请用 Python + PySCIPOpt 生成一个可导出 .lp 文件的优化模型，模型对象是 SF3-CT 四槽 process module + 双臂双指 robot 的 4x1 稳态调度问题。

设备与输入：
1. 有 n 道工艺，WFP=(m1,...,mn)，mi 是第 i 道工艺的并行 PM 数。
2. LL 作为 step 0 和 step n+1；dirty arm 只从 LL 向 step 1 搬 raw wafer；clean arm 负责 step 1 之后的 clean wafer 转运和回 LL。
3. 每个 PM 有 4 个 space，一次满腔处理 4 片 wafer。Robot 每次用一个双指臂搬 2 片，先装 W_i,12，再经 PM 内部旋转装 W_i,34；加工后按 FIFO 先卸 W_i,12，再旋转卸 W_i,34。
4. 输入参数包括 alpha_i 加工时间、delta_i 驻留时间上限、普通装卸时间 gamma、LL 取片含对齐时间 gamma0、robot 移动/换臂时间 beta、PM 内部旋转时间 upsilon。
5. 支持策略集合 strategies={OBS,OHTS,TBS,THTS}；如果只实现会议版，则支持 {BS,HTS}，其中 BS 对应 OBS 的 one-time backward 思想，HTS 对应 OHTS 的 one-time hybrid 思想。

变量：
- 对每个策略 s 建立连续变量 psi_s >= 0。
- 对每道工艺 i 建立 theta_i, d_i, tau_i_12, tau_i_34, omega_i1, omega_i2, omega_i3，均非负。
- 若要在一个 MIP 中选择策略，增加二进制变量 y_s，sum_s y_s = 1；否则为每个策略分别建一个 LP。

约束：
1. RTC: alpha_i <= tau_i_12 <= alpha_i + delta_i；alpha_i <= tau_i_34 <= alpha_i + delta_i。
2. 根据所选策略的 robot task sequence 推导 theta_i。形式为 theta_i = (alpha_i + d_i + 固定robot任务时间 + 固定PM旋转时间 + 相关omega之和) / m_i。
3. 根据所选策略推导 robot cycle time: psi_s = 固定周期robot任务时间 + 周期内 omega_i1/omega_i2/omega_i3 之和。
4. 稳态平衡: psi_s = theta_i for all i=1..n。
5. PM 旋转等待: omega_i2 >= upsilon - robot_tasks_executed_while_PM_rotates_before_unloading_W_i_34；omega_i3 >= upsilon - robot_tasks_executed_while_PM_rotates_before_loading_W_i_34；omega >= 0。若策略中某个等待不存在，则固定为 0。
6. sojourn time: tau_i_12 与 tau_i_34 必须由 alpha_i、d_i、PM 旋转时间、相关 robot 任务时间和等待时间线性表达出来，分别对应 W_i,12 和 W_i,34 从进入 PM 到被卸出的时间。
7. 如果使用 y_s 统一选择策略，用大 M 将每个策略的第 2-6 类约束改成只在 y_s=1 时生效；引入连续变量 psi，并约束 psi >= psi_s - M*(1-y_s)，目标为 min psi。不要在目标函数中使用 y_s * psi_s 这样的双线性乘积。

目标：
minimize psi_s（单策略 LP）或 minimize psi（统一策略选择 MIP）。

输出：
1. 生成函数 build_sf3ct_model(params, strategy=None, unified_strategy_selection=False)。
2. 写出清晰的变量命名。
3. 导出 .lp 文件。
4. 给一个 n=3, WFP=(1,1,1) 的示例参数，并能运行生成模型。
5. 在代码注释中说明：该模型是文献型稳态周期模型，不是有限批 wafer 级甘特图模型。
```

## 8. 当前仓库直接生成 4x1 全流程 MIP 的命令

若目标不是复现文献 LP，而是生成当前项目的端到端有限批 MIP，可使用：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name sf3_ct_4x1_fullflow.lp ^
  --num_batches 16 ^
  --num_pm 2 ^
  --num_steps 13 ^
  --mode_4x1_wafers 25 ^
  --mode_2x2_wafers 0 ^
  --pec_pool_size 8 ^
  --batch_size 4 ^
  --pm_rotation_time_180 2 ^
  --pair_transfer_time 4 ^
  --atr_transfer_time 3 ^
  --atr_return_time 3 ^
  --aligner_time 20 ^
  --llupper_time 30 ^
  --lllower_time 25 ^
  --full_process_time 80 ^
  --mix_boundary_process_time 30 ^
  --mix_internal_process_time 30 ^
  --cleaning_interval 10 ^
  --cleaning_process_time 60 ^
  --max_module_residency_time 80 ^
  --max_robot_residency_time 80 ^
  --pm_balance_penalty 0.01
```

生成结果会自动带日期后缀，并同时输出对应的模型说明 Markdown。
