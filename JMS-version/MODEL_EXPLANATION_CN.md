---
title: "批次任务调度模型：公式与实现说明"
subtitle: "全Pjob非递减取片 · 对内位置排程与晶圆身份解码 · 两阶段求解"
date: "2026年11月3日"
lang: zh-CN
---

# 1. 适用版本与阅读约定

本说明对应当前中文主稿 `JMS_Review_CN.tex`，以及独立实现 `model4_pjob_nondecreasing_20261102/`。输出版本标识为 `pjob_global_nondecreasing_v1`，出片规则标识为 `global_pjob_index_nondecreasing_lp_pickup`。同一Pjob按输入序号保持LP取片开始时刻非递减；同对、同LP且满足物理条件的相邻产品可同时取片。

`model4_pjob_fifo_20261029/` 是禁止同Pjob同步取片的历史严格版本，标识为 `pjob_global_fifo_v2`；更早的 `model4_pjob_20261027/` 只按Pjob--LP组恢复身份。三者的可行域和实验结果不能不加区分地混用。下文未特别标注的代码位置均指当前非递减版本。

本文按“物理含义、数学条件、实现位置”解释模型。公式中的PW对和周期编号从1开始，代码中从0开始；两者的对内位置均为$r\in\{0,1\}$。所有时间单位均为秒。公式中的条件式表示需线性化的逻辑，不表示求解器直接接受严格不等式或变量乘积。

模型联合决定产品组对、腔室分配、周期占位、辅助晶圆借用、清洁位置、搬运与资源次序。第一阶段最小化最后一片产品返回原LP的时间；第二阶段保持其上界和主要离散结构，改善等待与节拍。可行排程不等于最优排程，固定结构下的最优也不等于完整模型的最优。

# 2. 输入、索引与变量

## 2.1 全部参数与集合配置

表1按建模需要完整列出集合、实例输入、固定物理规则及其派生配置，默认数值以当前 `Config` 为准。输入集合不等于求解结果；解后确定的集合已单独标注，不要求用户提前枚举。表2仍仅列关键变量。

| 符号或配置项 | 类型 | 定义、取值及生成规则 |
|---------------------------|------------------|-------------------------------------------------------|
| $\mathcal J,\mathrm{Pjob}_j$ | 任务索引与产品集合 | $\mathcal J=\{1,\ldots,J\}$；产品按模式、腔室资格及调度属性分组，每片恰属一个任务。 |
| $\ell,s,\mathcal L_j,k,\ell_{jk}$ | LP、槽位与有序编码 | 四个LP，槽位$s=1,\ldots,25$；$\mathcal L_j$存任务$j$实际编号升序表，$k=1,\ldots,N_j$；来源$\ell_{jk}$由编号表确定。 |
| $N_{j\ell},N_j,N_\zeta,N_\psi,N$ | 库存及派生整数 | 各任务在各LP的产品库存；$N_j=\sum_\ell N_{j\ell}$，$N=N_\zeta+N_\psi=\sum_jN_j$，不含辅助片。 |
| $m_j,\mathcal M,\mathcal C,\mathcal C_j$ | 配方与资格集合 | $\mathcal M=\{\zeta,\psi,\mathrm{cl}\}$；设备腔室为CH2/CH3；任务模式$m_j$与非空资格$\mathcal C_j\subseteq\mathcal C$由输入给定。 |
| $\mathcal C(m)$ | 设备兼容集合 | 类型$m$可用的设备腔室；本设备两腔均支持两种配方及清洁，产品资格再由$\mathcal C_j$收紧。 |
| $\mathcal P,\mathcal Q_c,\mathcal I$ | 派生候选集合 | $\mathcal P=\{1,\ldots,P_{\max}\}$，$\mathcal Q_c=\{1,\ldots,Q_{\max}\}$；对内位置$r\in\{0,1\}$，路线任务$\mathcal I=\mathcal P\times\{0,1\}$。 |
| $T,J_{\max},P_{\max},Q_{\max}$ | 派生容量上界 | $T=N_\zeta+2N_\psi$，$J_{\max}=T$，$P_{\max}=N+3T$，$Q_{\max}=2T$；用于完整候选域，不是实际执行数量。 |
| $\mathcal S,\sigma$ | 来源集合与配置 | $\mathcal S=\{A,V\}$为大气/真空区域；单源$\sigma=0$，双源$\sigma=1$。产品均来自LP；辅助片分别来自AS或VS。 |
| $\mathcal D,D$ | 辅助身份集合与数量 | $\mathcal D=\{D_1,\ldots,D_D\}$，$D=\lvert\mathcal D\rvert$；基准按每腔4片配置，共享8片，非按腔独占；实现允许$4\le D\le10$。 |
| $\mathcal O,\mathcal O^{\rm occ}$ | 派生动作与占用集合 | 由候选晶圆路线任务、周期及路线模板生成物理动作和资源占用区间；占用端点引用取放、旋转与加工事件。 |
| $\mathcal R,K_\rho,\Gamma_o$ | 资源类、容量与允许单元 | ATR承2片、VTR承4片，AL容量1，上/下LL各2槽，腔室4工位；机器人及腔室执行机构各为独占资源；$\Gamma_o$为占用允许单元集合。 |
| $\mathcal A^{\rm int},\mathcal A_{is}(\gamma),\mathcal A$ | 路线模板与启用弧集 | 腔内公共先后弧及按来源、成对搬运/随行选择启用的供回弧；完整弧集由模板和选择确定，并非预先固定的完整动作次序。 |
| $\mathcal V_c,e,\nu$ | 解后派生区段索引 | 生产任务集$\mathcal V_c$、清洁区段$e$及清洁阶段$\nu\in\{FL,BL,P,BU,FU\}$由周期结构及物理事件恢复，不是独立输入分段。 |
| $\mathcal W,\mathcal I_h,\mathcal D_{\rm fix}$ | 评价与阶段二派生集合 | 等待项集由路线间隔生成；节拍中心集$\mathcal I_h$由连续保留链确定；固定分量集$\mathcal D_{\rm fix}$包含除原子同步外的非连续变量。 |
| $d_\zeta,d_\psi,d_{\mathrm{cl}}$ | 正实数时长 | 两种生产及清洁曝光默认180、90、500 s；$2\times2$产品需相邻两次90 s曝光。 |
| $d_o^{\rm ATR},d_o^{\rm VTR},r_c$ | 正实数时长 | ATR取放4 s、VTR取放1 s、腔室半周旋转2 s；共同装卸对只执行一次原子动作，LP取片时长为正。 |
| $t_{\rm ATR},t_{\rm VTR},t_{\rm empty}$ | 移动时间配置 | 通常换位分别3、2 s；ATR从LL空返LP或AS再取片为6 s；同地点及U/L间移动取0，按地点与方向生成换位参数。 |
| $t_{\rm AL},t_{\rm pump},t_{\rm vent}$ | 必要工艺间隔 | 产品AL对准20 s、上锁抽气30 s、下锁放气25 s；辅助片不执行AL对准。 |
| $t_{\rm U}^{\rm reset},t_{\rm L}^{\rm reset}$ | 槽位复位时长 | 上/下LL槽位分别30、25 s，从另一侧取片结束后计；可与取片后运输重叠。 |
| $d_o,\delta_{oo'},\delta^\rho_{oo'}$ | 按模板派生的时长参数 | 物理动作持续时间、技术弧最小间隔及方向相关换位/复位间隔，由上述时长、地点与物理路线生成，不额外任意赋值。 |
| $H$ | 清洁阈值 | 整数$H\ge2$，默认3；累计1至$H-1$次可在合法边界提前清洁，达到$H$必须清洁，包括末段。 |
| $\overline R_{i\rho}$ | 硬驻留/承片上限 | 模块驻留与机械手承片上限默认各10000 s；模块按放片结束至取片开始计，手按取片开始至放片结束计。 |
| $\overline T,M,B$ | 时域与派生松弛量 | 时域默认100000 s；$M=3\overline T+\max(t_{\rm pump},t_{\rm vent},t_{\rm U}^{\rm reset},t_{\rm L}^{\rm reset})$；资源平移带宽$B=\overline T+\max(0,t_{\rm U}^{\rm reset},t_{\rm L}^{\rm reset})$。 |
| 辅助片对准策略 | 路线配置 | 当前为不对准，可单独绕过AL或随产品到AL而留在ATR上；旧全片对准选项仅用于历史规则，不能与当前输入混用。 |
| VTR洁净/脏手策略 | 承片资格配置 | 当前未加工产品用两只脏手、加工完成产品用两只洁净手，辅助片可用全部四手；旧不区分手的选项属不同物理规则。 |
| Pjob出片与设备容量规则 | 固定模型配置 | 同Pjob跨LP按输入序号非递减取片；同对同LP允许同步，仍满足容量与动作互斥；不同Pjob可交错；每个PW对2片、每个腔室周期2对满片。 |
| $\lambda_1,\lambda_2,\lambda_3,\varepsilon_C$ | 阶段二配置 | 总等待、最大等待及节拍绝对偏差权重为$(1,10,25)$，产品完工上界容差$10^{-6}$ s；固定第一阶段主要离散结构。 |
| $\bar\omega_\alpha,\lambda_4$ | 未启用的扩展配置 | 可选软等待上限及超额罚权重；当前默认实现不生成该项。它们不是当前实验必须提供的输入。 |

Table: 模型所需的参数与集合配置

每腔4片是基准库存总量配置规则，不是按腔专属分配；两腔共享8片，可用片数还取决于归还时刻。实例允许覆盖默认数值，不能把默认值写成全部实验的共同输入。

代码 `self.H` 表示时域 `horizon`，公式中的$H$才表示清洁阈值；两者不可混淆。资源移动参数在本文式(22)简记为$\rho_{ii'}$，文稿写作$\delta^\rho_{oo'}$。等待集合在文稿记为$\mathcal W$。

**配置字段覆盖。** 当前 `Config` 的全部27个字段及其表1含义如下；`pjobs`嵌套记录必须含任务ID、模式、允许腔室和产品ID列表。未显式提供Pjob时按代码默认组建，不能误用为已经给定专属腔室资格。

`load_ports`：LP库存与实际编号；`pjobs`：任务ID、模式、资格、产品ID列表；`source`：来源集合与单/双源配置；`dummy_alignment`：辅助片对准策略；`vtr_hand_policy`：VTR洁净/脏手策略。

`dummy_count`：辅助身份集合与数量；`cleaning_interval`：清洁阈值；`full_time`：4x1曝光；`mix_time`：2x2曝光；`cleaning_time`：清洁曝光。

`handling`：VTR取放；`atr_handling`：ATR取放；`atr_empty_ll_to_lp`：ATR从LL空返源端；`rotation`：半周旋转；`atr_travel`：ATR通常移动。

`vtr_travel`：VTR通常移动；`alignment`：AL对准；`pump`：上锁抽气；`vent`：下锁放气；`upper_reset`：上锁复位。

`lower_reset`：下锁复位；`module_residency`：模块驻留上限；`robot_residency`：手上承片上限；`horizon`：时域；`max_pairs`：候选对容量。

`max_cycles`：每腔候选周期容量；`chambers`：设备腔室集合。

`max_pairs=max_cycles=0`表示自动取完整候选上界，不是零候选。可显式放大容量；小于安全上界时会标记受限候选域。阶段二权重与容差当前在实现中固定；软等待上限是未启用扩展，不在 `Config` 中。求解时限、种子、内存、并发、初始化预算是实验协议，另见实验命令文档。

## 2.2 关键决策变量与辅助量

| 符号 | 类型及含义 |
|---|---|
| $x_{j\ell pr}$ | 二元：PW对$p$的位置$r$选择任务$j$在LP $\ell$的一片产品；不直接选择实际晶圆编号 |
| $v_p,\mu_{pm},z_{pc}$ | 二元：对启用、类型选择、腔室选择 |
| $\beta_{pr},d_{pr}$ | 派生0--1量：产品标记、辅助片需求标记 |
| $X_{pcq},A_{pcq},f_{pcq}$ | 二元：占位、首次进入、加工时前侧占位 |
| $K_{cqm},U_{cq}$ | 周期类型选择；周期启用$U=\sum_m K$ |
| $g_{pr\tau},h_{iu},y_{ii'}$ | 辅助身份、资源单元、互斥次序选择 |
| $\gamma_{pa}$ | 同对两片晶圆在搬运段$a$同步的选择 |
| $s_o,S_{cq},\theta_{j\ell}$ | 非负连续：动作、周期开始、跨LP取片分界 |
| $n_{cq}$ | 非负整数：周期后累计生产次数 |
| $C_{\max},L_{\max},v_{cq}$ | 非负连续：产品完工、最大等待、节拍偏差上界 |

Table: 批次任务调度的关键决策变量

注意$v_p$与$v_{cq}$是不同量，$d_{pr}$是辅助标记，$d_o$是动作时长。固定时长动作的结束时刻是表达式，不另生成结束变量；逻辑缓存列即使出现在求解器中，也不一定代表新的物理选择。

# 3. 批次内编码、非递减取片与具体晶圆解码

## 3.1 编码表

LP $\ell$中槽位$s$的实际晶圆编号为$w=25(\ell-1)+s$。将任务$j$的实际编号按升序存为有序表$\mathcal L_j$：

$$
\begin{aligned}
\mathsf{Code}(\mathcal L_j[k])&=\mathrm{Pjob}_j[k],\\
\ell_{jk}&=1+\left\lfloor\frac{\mathcal L_j[k]-1}{25}\right\rfloor,\\
N_{j\ell}&=|\{k:\ell_{jk}=\ell\}|.
\end{aligned}\tag{1}
$$

编码先按调度属性确定任务$j$，再在任务内将实际编号升序排列。对$w\in\mathcal L_j$，其位置为$k_j(w)=1+|\{u\in\mathcal L_j:u<w\}|$，因此$\mathsf{Code}(w)=\mathrm{Pjob}_j[k_j(w)]$；逆映射为$\mathsf{Code}^{-1}(\mathrm{Pjob}_j[k])=\mathcal L_j[k]$。$\mathcal L_j$是可按下标访问的有序表。$\mathsf{Code}$在建模前确定，只变换编号；热启动的$\mathsf{Enc}$将完整物理排程写成变量赋值，最终的$\mathsf{Dec}$则输出含实际身份和全部动作时刻的晶圆排程，三者不是同一个映射。

例如$\mathcal L_1=(1,3,26,27)$，则Pjob1[1]至[4]分别映射到上述四片产品，前两片来自LP1，后两片来自LP2。取片序列中可以穿插其他Pjob，但Pjob1必须保持1、3、26、27的取片开始时刻非递减。例如晶圆1与3可以在同一PW对内同时从LP1取片，26与27同理；不同LP不能仅因允许等号就同步执行ATR取片。**该规则只约束源端取片，不要求后续加工或回片全程FIFO。**

## 3.2 库存选择与跨LP分界

不为每片实际产品建立身份到对内位置的选择变量，而选择其Pjob和LP库存：

$$
\sum_{p,r}x_{j\ell pr}=N_{j\ell},\qquad
\beta_{pr}=\sum_{j,\ell}x_{j\ell pr},\qquad
\beta_{pr}+d_{pr}=v_p.\tag{2}
$$

每个启用对恰有两片晶圆；库存守恒仅解决“用了多少片”，不能单独保证跨LP取片顺序。令$h_j(\ell)$为任务$j$的下一个非空LP，引入连续分界$\theta_{j\ell}$：

$$
\begin{aligned}
0\le\theta_{j\ell}&\le\overline T,\\
s^{\rm pick}_{pr}&\le\theta_{j\ell}+M(1-x_{j\ell pr}),\\
s^{\rm pick}_{pr}&\ge\theta_{j\ell}-M(1-x_{j,h_j(\ell),pr}).
\end{aligned}\tag{3}
$$

选择左侧LP库存的产品须在分界时刻或之前开始取片，选择下一非空LP库存的产品须在分界时刻或之后开始取片。串联相邻非空LP即可保证整批跨LP的开始时刻次序。分界不再使用前一LP的取片结束时刻；跨LP动作的实际不重叠和换位要求仍由ATR资源约束保证。

令$s^{\rm pick}_{jk}$引用解码后$\mathrm{Pjob}_j[k]$所在对内位置的取片开始时刻，则批次内规则为

$$
s^{\rm pick}_{j,k+1}\ge s^{\rm pick}_{jk},
\qquad j\in\mathcal J,\quad k=1,\ldots,N_j-1.\tag{4}
$$

这里的$s^{\rm pick}_{jk}$是已有事件时刻的引用，不另增加逐片时间变量。库存模型通过式(2)、式(3)及第3.3节的确定性解码落实式(4)，不是先为实际编号建立逐片指派变量。

旧版限制$\gamma_{p,\rm pick}+\sum_\ell(x_{j\ell p0}+x_{j\ell p1})\le2$已撤销。同一Pjob的相邻两片产品分配至同一PW对、来自同一LP且满足物理条件时，可取$\gamma_{p,\rm pick}=1$，两片的取片开始和结束时刻均相同。允许等号不等于把取片时长设为零：共同动作仍持续正的ATR取片时长，并占用两个承片位置。

分配到同一PW对并不强制同步取片；当$\gamma=0$时，两片仍由动作互斥排序。同对不同LP不能同步取片，不同PW对也不能同时占用ATR执行两个冲突动作。同一任务的顺序只约束源端取片，不额外要求加工、卸载和回片保持相同次序。

对应：`pjobs.py::groups_from_config`；`pjob_order.py`中的`encoding`、`add_release_boundaries`、`decode_members`和`order_report`。`restrict_pick_sync`保留调用接口但直接返回，不再添加同Pjob同步禁令；物理同步与互斥仍由`model.py::resources`等模块处理。

## 3.3 从PW对内位置恢复具体晶圆编号

**$x_{j\ell pr}$不能单独确定实际晶圆编号，但它选择的对内位置已经具有完整排程。** 对内位置$r$是PW对中两片晶圆的索引，不等于LP槽位、物理手或腔室工位。模型为$i=(p,r)$建立逐片取放与承片区间，将其联结到PW对$p$的腔室选择、装卸和加工周期。因此，这不是先求一个没有单片路线的批次排程，再临时补排每片动作；后处理只恢复实际身份，不重新安排路线和时刻。

设安排任务$j$产品的对内位置组成集合

$$
\mathcal I_j=\{(p,r):\sum_\ell x_{j\ell pr}=1\}.
$$

对该集合按“LP取片开始时刻、来源LP编号、对编号$p$、对内位置$r$”依次升序排列，得到$i_j^{(1)},\ldots,i_j^{(N_j)}$，再执行

$$
i_j^{(k)}\longmapsto\mathrm{Pjob}_j[k]
\longmapsto\mathcal L_j[k].
$$

库存守恒保证产品晶圆数量正确，跨LP分界保证来源次序，解码再检查所选LP与输入编码表一致。实际编号沿对内位置的全部取片、搬运、加工和回片事件传播，得到“晶圆编号—PW对—对内位置—具体动作”的完整对应。

下表沿用$\mathcal L_j=(1,3,26,27)$。时刻仅用于说明身份映射，不是已经验证的完整设备排程；对编号使用本文从1开始的记法。

| 已选对内位置$(p,r)$ | 来源 | 取片开始/s | 恢复的任务内编码 | 实际晶圆编号 |
|---|---|---:|---|---:|
| $(1,0)$ | LP1 | 10 | Pjob$j$[1] | 1 |
| $(1,1)$ | LP1 | 10 | Pjob$j$[2] | 3 |
| $(2,0)$ | LP2 | 30 | Pjob$j$[3] | 26 |
| $(3,0)$ | LP2 | 50 | Pjob$j$[4] | 27 |

前两片在同一个PW对内同时取片，按对内位置$r$确定相邻编号。晶圆1执行对内位置$(1,0)$的全部动作，晶圆3执行$(1,1)$的全部动作，二者的取片时刻仍相等。这个同刻编号规则用于输出的确定性，不增加物理上的先后时间间隔。

## 3.4 等价表示的前提与逐片对照

当前聚合的前提是：**同一Pjob、同一LP内的产品，在模型涉及的工艺、资格、释放条件和取放规则上可互换。** 输入实际槽位用于编号及批次内顺序；当前模型没有逐槽位不同的取片时长或可访问性约束。若存在晶圆专属释放时刻、处理时间、资格或槽位取片限制，必须在输入分组与约束中显式表达；直接按库存聚合后再赋予编号可能不成立。

逐片对照使用$y_{wpr}=1$直接表示实际产品$w$分配给对内位置$(p,r)$。其与库存表示的投影关系为

$$
x_{j\ell pr}=\sum_{w\in\mathcal W_{j\ell}}y_{wpr},
$$

其中$\mathcal W_{j\ell}$是输入给定的任务$j$在LP $\ell$中的实际产品集合，与等待项集合$\mathcal W$不同。两种表示共用各对内位置对应晶圆的路线、完整候选容量和物理资源约束。逐片对照另设每片取片时刻并与被选对内位置联结，同Pjob相邻时刻只要求大于等于，不再加ATR取片时长。

同任务、同LP的两片产品同时取片时，逐片选择可以给出与库存规范解码不同的同刻身份排列。新验解允许仅在这些同属性、同刻产品间置换，并保存显式选择供复核；跨任务、跨LP或取片时刻不同的身份交换不接受。两种表示的等价性是物理排程与目标值的等价，不要求每个同时取片的对内位置上的身份命名都相同。

对应两个对照构造器：`experiments/nondecreasing_strengthening_20261102/strengthen_models.py::build`与`experiments/nondecreasing_followup_20261102/followup_models.py::build_fair`；同刻身份检查见前者的`assert_wafer_decode`。

# 4. PW对类型、腔室资格与候选容量

## 4.1 组对与分腔

$$
\begin{aligned}
\sum_m\mu_{pm}&=v_p,&\sum_cz_{pc}&=v_p,\\
x_{j\ell pr}&\le\mu_{p,m_j},&
x_{j\ell pr}&\le\sum_{c\in\mathcal C_j}z_{pc}.
\end{aligned}\tag{5}
$$

同对产品须同配方，所选腔室须在其资格集合的交集内。例如仅CH2与仅CH3的产品不能组对；两腔均可的产品可以与任一专属任务的同配方产品组对。辅助片可补位；清洁对只能包含辅助片。

以$F_p$标记含产品对，以$F_p^\psi$标记含链式产品的对：

$$
\begin{aligned}
F_p\le\sum_r\beta_{pr}&\le2F_p,&F_p+\mu_{p,\mathrm{cl}}&\le1,\\
F_p^\psi\le F_p,\quad F_p^\psi&\le\mu_{p\psi},&
F_p^\psi&\ge F_p+\mu_{p\psi}-1.
\end{aligned}\tag{6}
$$

这些是“逻辑与”的线性联结，不直接使用二元乘积。

## 4.2 容量不是实际执行次数

$$
\begin{aligned}
T&=N_\zeta+2N_\psi,&J_{\max}&=T,\\
P_{\max}&=N+T+2J_{\max},&Q_{\max}&=T+J_{\max}.
\end{aligned}\tag{7}
$$

每个生产周期至少含产品，故生产周期数不超过$T$。禁止初始空清洁和连续清洁，因此清洁数不超过$T$。含产品对至多$N$个，生产补位对至多$T$个，每次清洁再预留两个辅助对，得到$P_{\max}$。$2\times2$产品对跨两个周期仍占一个对编号。

$Q_{\max}$是全设备周期总数上界，并对每个腔室提供这么多候选编号；额外施加全设备周期和清洁总数上界。缩小这些容量可能收紧可行域，不能继续宣称是在完整候选域中求解。

含产品对与纯辅助对分开编号和前缀激活。含产品对至多$N$个，其位置$r=0$可规范为产品，因而只在前$N$个候选对生成产品选择变量。令$G=|\{(j,\ell):N_{j\ell}>0\}|$、$J=|\mathcal J|$：库存选择块有$2GN$个二元变量，跨LP分界有$G-J$个连续变量。这两个数字不是模型总变量数。

对应：`joint_pairing_model.py::add_pjob_pairing`；`model.py::Integrated.__init__`。

# 5. 四工位满片加工与连续两次曝光

## 5.1 每周期两个PW对

$$
\begin{aligned}
U_{cq}&=\sum_mK_{cqm}\le1,&\sum_pX_{pcq}&=2U_{cq},\\
X_{pcq}&\le z_{pc},&X_{pcq}+\mu_{pm}&\le1+K_{cqm},\\
\sum_pX^P_{pcq}&\ge K_{cq\zeta}+K_{cq\psi},&U_{c,q+1}&\le U_{cq},\\
\sum_{c,q}U_{cq}&\le Q_{\max},&\sum_{c,q}K_{cq,\mathrm{cl}}&\le J_{\max}.
\end{aligned}\tag{8}
$$

其中$X^P=X\land F$通过$X^P\le X$、$X^P\le F$、$X^P\ge X+F-1$线性化。每个启用周期恰有两个对，即四片占位；生产至少含一个产品对，清洁仅含辅助对。前缀启用只消除空编号，不固定实际加工类型的顺序。

## 5.2 首末占位与连续性

取边界$X_{pc0}=X_{pc,Q_{\max}+1}=A_{pc,Q_{\max}+1}=0$，首周期$A_{pc1}=X_{pc1}$。其余周期：

$$
\begin{aligned}
A_{pcq}&\ge X_{pcq}-X_{pc,q-1},\\
A_{pcq}&\le X_{pcq},\quad A_{pcq}\le1-X_{pc,q-1},\\
Z_{pcq}&=X_{pcq}-X_{pc,q+1}+A_{pc,q+1},\\
\sum_{c,q}A_{pcq}&=v_p,\qquad
\sum_{c,q}X_{pcq}=v_p+F_p^\psi.
\end{aligned}\tag{9}
$$

一次进入加总占位数为1或2，使每个启用对形成长度1或2的连续段。$4\times1$产品参加一次生产；$2\times2$产品在同一腔室相邻两周期连续加工，中间不能卸出或插入清洁。纯辅助补位对、清洁对各参加一次周期。

再要求

$$
\sum_p(X_{pcq}-Z_{pcq})\le1,\qquad
\sum_p(X_{pcq}-A_{pcq})\le1,\tag{10}
$$

每个链式周期至多有一个首次曝光产品对和一个末次曝光产品对，实现交替保留与换片链。

对应：`joint_chamber_cycle_model.py::add_chamber_cycles`。

# 6. 时刻、路径与腔室旋转装卸

## 6.1 固定时长与先后弧

动作$o$的启用量为$b_o$、持续时间为$d_o$：

$$
e_o=s_o+d_ob_o,\qquad
0\le s_o,e_o\le\overline T b_o.\tag{11}
$$

未启用动作归零，启用动作时长固定。等待放在动作之间，不能通过拉长取放或旋转矩形冒充加工时间。若某路线弧由$a_{oo'}$启用，所需间隔为$\delta_{oo'}$：

$$
s_{o'}\ge e_o+\delta_{oo'}-M(1-a_{oo'}).\tag{12}
$$

激活量须联结正确路线及前后事件。指示等式$t=t'$用$-M(1-a)\le t-t'\le M(1-a)$线性化。本文公式写时域$\overline T$，实现取$M=3\overline T+\max\{\text{抽气、放气、上下锁复位}\}$；不得随意调小$M$。

## 6.2 单源与双源

令$\sigma=0$为单源、$\sigma=1$为双源，晶圆路线任务$i=(p,r)$的区域标记为

$$
\chi_{iA}=\beta_{pr}+(1-\sigma)d_{pr},\qquad
\chi_{iV}=\sigma d_{pr},\qquad
\chi_{iA}+\chi_{iV}=v_p.\tag{13}
$$

产品总是按LP、AL、上LL、腔室、下LL、原LP的顺序运行。单源辅助片从大气存储AS进出，通过ATR、LL、VTR；双源辅助片从真空存储VS进出，只需VTR。辅助片不需要AL对准。单源/双源不是LP数量的区别。

同对两片晶圆在某个同地点搬运段同步时，$\gamma_{pa}=1$强制其起止时刻相等；仅在这个同步组内部免除动作互斥。两片仍各占一个物理承片位置。资格、来源及同Pjob非递减取片规则仍须满足；同对同LP的相邻产品可以同步取片。

单源产品--辅助对还有三选一：辅助片先入LL、产品放到AL后再取辅助片、或辅助片随产品到AL并在ATR上等待。设该产品--辅助配对的启用量为$a$，有

$$
\gamma^{\rm early}+\gamma^{\rm late}+\gamma^{\rm escort}=a.\tag{14}
$$

先行分支要求辅助入LL结束不晚于产品放AL开始；后取分支要求辅助源端取片不早于产品放AL结束。随行分支要求辅助在产品放AL前已被取出，并与对准完成后的产品同步放入上LL。辅助片在此期间持续占ATR一只手；不同源位置的取片不被强制同步。

## 6.3 周期时长和前后侧

$$
\begin{aligned}
E_{cq}&=S_{cq}+\sum_md_mK_{cqm},\\
0\le S_{cq},E_{cq}&\le\overline T U_{cq},\\
S_{cq}&\ge E_{c,q-1}-M(1-U_{cq})\quad(q>1).
\end{aligned}\tag{15}
$$

旋转、装卸另外计时，不能只用式(15)替代整套腔室物理约束。令$\kappa$表示从上一周期保留一个对，$\upsilon$表示本周期后全部退出：

$$
\begin{aligned}
\kappa_{cq}&=\sum_p(X_{pcq}-A_{pcq}),\\
\upsilon_{cq}&=U_{cq}-\sum_p(X_{pcq}-Z_{pcq}),\\
f_{pcq}&\le A_{pcq},\qquad\sum_pf_{pcq}=U_{cq},\\
f_{pc,q-1}&\ge X_{pcq}-A_{pcq}\quad(q>1),\\
f_{pcq}&\ge F_p+K_{cq\psi}+X_{pcq}-2-\kappa_{cq}.
\end{aligned}\tag{16}
$$

新装前侧对在周期前旋转后装入，前侧装载结束即开始加工；新装后侧对在该旋转之前装入。保留对上周期必须在前侧，旋转后位于后侧。链首$2\times2$产品对最后装入前侧。

具体时间联结如下，均只在对应占位条件为真时启用：

$$
\begin{aligned}
X=1&\Rightarrow S_{cq}\ge e_p^{\rm load},\quad s_p^{\rm unload}\ge E_{cq},\\
A=1,f=0&\Rightarrow e_p^{\rm load}\le s_{cq}^{\rm rot-},\\
A=1,f=1&\Rightarrow s_p^{\rm load}\ge e_{cq}^{\rm rot-},\quad S_{cq}=e_p^{\rm load},\\
Z=1,f=1&\Rightarrow e_p^{\rm unload}\le s_{cq}^{\rm rot+},\\
Z=1,f=0,\upsilon=1&\Rightarrow s_p^{\rm unload}\ge e_{cq}^{\rm rot+},\\
Z=1,f=0,\upsilon=0&\Rightarrow s_p^{\rm unload}\ge e_{c,q+1}^{\rm rot-}.
\end{aligned}\tag{17}
$$

保留边界的周期前旋转须在上一周期曝光结束后进行；全部退出时的周期后旋转须在曝光结束后进行。下一周期装载还要等待应退出的旧对卸完。这些联结与VTR互斥共同阻止“腔内仍有未卸晶圆却装新片”。前后侧是随旋转改变的位置，不是永久产品类别。

对应：`model.py::event`、`route`、`accompaniment`、`chambers`。

# 7. 提前清洁与达到阈值强制清洁

令$n_{cq}$为周期$q$完成后自上次清洁以来的生产次数，$n_{c0}=0$，尾部$U_{c,Q_{\max}+1}=0$：

$$
\begin{aligned}
0\le n_{cq}&\le HU_{cq},\\
K_{cq,\mathrm{cl}}=1&\Rightarrow n_{cq}=0,\quad 1\le n_{c,q-1}\le H,\\
U_{cq}=1,\ K_{cq,\mathrm{cl}}=0
&\Rightarrow n_{cq}=n_{c,q-1}+1,\quad n_{c,q-1}\le H-1,\\
n_{cq}&\le H-1+HU_{c,q+1},\\
K_{c1,\mathrm{cl}}&=0,\quad
K_{cq,\mathrm{cl}}+K_{c,q-1,\mathrm{cl}}\le1\quad(q>1).
\end{aligned}\tag{18}
$$

式(18)同时表达四件事：生产一次加1；清洁归零；已有1至$H-1$次生产时允许提前清洁；达到$H$时下一启用周期必须清洁。尾部不允许以计数$H$终止，故最后一段达到阈值也必须追加清洁。末段小于$H$则可不清洁。

以$H=3$为例，生产、清洁、生产是允许的提前清洁；生产、生产、生产后必须清洁。对于$2\times2$产品，阈值按两次曝光分别计数，但清洁不得插在它的两次连续曝光之间：若只剩一次计数余量，不能启动一个需要连续两次曝光的新产品对，应在合法边界先清洁。

“低于阈值都能清洁”并不允许尚未生产就空清洁，也不允许连续清洁、破坏连续曝光或违反满片资源条件。一次清洁需要四片辅助片、两个PW对，以及完整的装载、旋转、500秒清洁曝光、卸载和归还；清洁曝光时长不是完整清洁任务时长。

实现采用线性计数界而非强制每$H$次才清洁。例如令$k=K_{cq,\mathrm{cl}}$、$u=U_{cq}$、$p^{\rm prod}=K_{cq\zeta}+K_{cq\psi}$：

$$
\begin{aligned}
n_{cq}&\le H(1-k),\quad n_{c,q-1}\ge k,\\
-(H+1)(k+1-u)&\le n_{cq}-n_{c,q-1}-p^{\rm prod}\\
&\le(H+1)(k+1-u).
\end{aligned}\tag{19}
$$

式(19)与式(18)中的后继、前缀及上界条件共同使用，不可只保留其中一条。

对应周期模块 `joint_chamber_cycle_model.py` 中的 `add_chamber_cycles` 函数。

# 8. 辅助片复用、承片容量与资源互斥

## 8.1 实体辅助片借用

$$
\sum_{\tau\in\mathcal D}g_{pr\tau}=d_{pr},\qquad
g_{p0\tau}+g_{p1\tau}\le1.\tag{20}
$$

每项辅助片借用需求恰借用一片实体辅助片，同对不能借同一片两次。占用区间从源存储取片开始到归还完成；不同腔室借用同一身份也必须互斥。辅助片数与辅助片借用任务数不是一个量：8片实体可以被许多对依次复用。

归还完成约束的是同一实体的再次借用，不表示每次归还都会推迟后续加工。例如，某片尚未归还时，下一次需求仍可选择库存中的另一片可用辅助片；只有在所选身份相同时，后一次借用才必须等待前一次归还。即使出现该等待，也须结合其他工艺前后关系和搬运资源时序，判断它是否推迟产品加工或批次完工。因此，不能仅凭复用约束或库存总量宣称“辅助晶圆返回影响后续加工”，应检查具体身份分配、完整借用区间及相应排程。

## 8.2 执行动作与承片容量分开

ATR可承2片，VTR可承4片，但每台机械手同一时刻只能执行一个协调搬运动作。AL容量为1，上LL和下LL各有2槽。VTR未加工产品使用两只脏手，已完成产品使用两只洁净手；辅助片可使用任一空闲手。成对搬运仍占两个承片位置。

启用的占用区间$i$从允许单元集合$\Gamma_i$选一个单元：

$$
\sum_{u\in\Gamma_i}h_{iu}=b_i.\tag{21}
$$

相同资源单元上的两个区间必须选择一种次序。若$y_{ii'}=1$表示$i$在前：

$$
\begin{aligned}
s_{i'}&\ge e_i+\rho_{ii'}-M(1-y_{ii'})-M(2-h_{iu}-h_{i'u}),\\
s_i&\ge e_{i'}+\rho_{i'i}-My_{ii'}-M(2-h_{iu}-h_{i'u}).
\end{aligned}\tag{22}
$$

机器人动作的$\rho$包括方向和地点相关换位；同一手的承片区间互斥则不额外计移动。上下锁槽位的占用从放片开始延续至另一侧取片完成，再加相应复位尾部。复位可以与已经离开该槽位的机械手运输重叠。

## 8.3 当前紧凑互斥实现

多单元资源并非逐单元重复生成式(22)。实现用单元编号$r_i=\sum_{u=1}^R u h_{iu}$，取$B=\overline T+\max(0,\text{上锁复位},\text{下锁复位})$，$\epsilon_{ii'}=2-b_i-b_{i'}$：

$$
\begin{aligned}
s_{i'}+B(r_{i'}-r_i)&\ge e_i-B(R+1)(1-y_{ii'}+\epsilon_{ii'}),\\
s_i-B(r_{i'}-r_i)&\ge e_{i'}-B(R+1)(y_{ii'}+\epsilon_{ii'}).
\end{aligned}\tag{23}
$$

同编号时平移抵消，约束物理互斥；不同编号时落在不同时间带，允许原时间区间重叠。该替换用于槽位、手和辅助身份区间，机器人执行动作及其移动仍单独约束。ATR的承片数以按动作排序的取放增量前缀计算，VTR还保留脏/净手分配；说明式(21)是统一物理表述，不代表每类资源都生成相同变量块。

## 8.4 硬驻留上限

模块驻留从放片完成算到取片开始；机械手承片从取片开始算到放片完成：

$$
\begin{aligned}
0\le s_i^{\rm module\ out}-e_i^{\rm module\ in}&\le\overline R^{\rm module},\\
0\le e_i^{\rm hand\ put}-s_i^{\rm hand\ pick}&\le\overline R^{\rm hand}.
\end{aligned}\tag{24}
$$

均为启用区间的条件约束。模块上限覆盖AL、上/下LL及腔室；机械手上限覆盖承片全段。驻留上限不等于“各片驻留时间必须相同”。循环等待若构成含正持续时间的约束环，沿环相加会产生矛盾，因此被时间可行性排除；这不是对任意未建模现场故障的保证。

对应：`model.py::resources`、`capacity`、`colored_nonoverlap`、`add_interval`；`physical_validate.py`。

# 9. 产品完工时间优先的两阶段目标

## 9.1 第一阶段

$$
\min_{\xi\in\mathcal F}C_{\max},\qquad
C_{\max}\ge e_{pr,\mathrm{return}}-M(1-\beta_{pr}).\tag{25}
$$

$\mathcal F$包含前述全部约束。$C_{\max}$是最后一片产品返回原LP的时间，不是最后曝光结束，也不是所有辅助归还和末端清洁结束。代码分别建立产品、辅助候选路线，未启用产品路线结束为0，因此直接对产品路线的回片结束加下界。

末端强制清洁仍须排入时域并满足资源约束，但其结束时刻不直接成为产品$C_{\max}$下界。它仍可能与其他腔产品争用VTR而间接影响目标。若统计WPH，采用$3600N/C_{\max}$。

## 9.2 第二阶段的实际求解范围

第一阶段返回一个已验解的可行解$\widehat\xi$，产品完工时间为$\widehat C$。当前实现固定全部非连续变量，但名称为 `sync_` 的同步选择例外：

$$
\xi_d=\widehat\xi_d\quad(d\in\mathcal D_{\rm fix}),\qquad
C_{\max}\le\widehat C+10^{-6}.\tag{26}
$$

固定内容包含库存配对、分腔、周期、清洁、辅助身份、手/槽位、资源次序、随行分支、整数计数和相关非连续辅助量。连续时间和同地点原子搬运同步选择继续优化。第二阶段在这个受限域中精修，并不搜索所有具有最佳$C_{\max}$的结构。因此“先完工时间、后等待”的实现不能写成已经完成全可行域的严格词典序全局优化。

第一阶段限时但有可行解时也能进入第二阶段；第一阶段无可行解则不能。第二阶段最优状态只证明受限精修问题最优，主问题证据仍查看 `primary_status`、`primary_bound` 和 `primary_gap`。

## 9.3 等待项

对路线间隔$\alpha$，扣除必要时长$\delta_\alpha$后的余量为

$$
\omega_\alpha=s_{\rm next}-e_{\rm previous}-\delta_\alpha b_i\ge0,\qquad
L_{\max}\ge\omega_\alpha.\tag{27}
$$

当前对产品和辅助候选路线均计入相应等待。未启用路线贡献0。具体区间包括VTR源端取片结束到腔室装载开始、腔室卸载结束到VTR目的端放片开始；大气路线另计源端至AL/LL、AL对准、上锁抽气、下锁放气及回源间隔。`model.py`中的`legs`列表定义精确统计集合。必要搬运、对准及压力转换时间已扣除；不同晶圆同时等待仍分别求和，不能把总等待当作设备时间轴空闲时长。等待为差分表达式，$L_{\rm sum}=\sum\omega$仅为统计简称。

## 9.4 节拍项与默认目标

只在同腔同一$2\times2$链的连续三个周期上计算节拍，两处边界均须保留一个对，即$\kappa_{cq}=\kappa_{c,q+1}=1$。令这些中心构成$\mathcal I_h$：

$$
\begin{aligned}
\Delta_{cq}&=S_{c,q+1}-2S_{cq}+S_{c,q-1},\\
v_{cq}&\ge\Delta_{cq},\quad v_{cq}\ge-\Delta_{cq},\quad v_{cq}\ge0,\\
\min\quad &\sum_\alpha\omega_\alpha+10L_{\max}
+25\sum_{(c,q)\in\mathcal I_h}v_{cq}.
\end{aligned}\tag{28}
$$

$\Delta$是相邻两个周期开始间隔之差，不是晶圆驻留差。代码以右端周期索引$q$写$S_q-2S_{q-1}+S_{q-2}$，与中心索引形式一致。没有有效三周期链时，节拍项没有实际评价对象，不能据总目标下降宣称节拍改善。限时解中的上界变量未必取紧，各指标应从事件重新计算。

正文还给出软等待上限扩展：$\eta_\alpha\ge\omega_\alpha-\bar\omega_\alpha$、$\eta_\alpha\ge0$，再将$\lambda_4\sum\eta$加到目标。**当前默认代码没有生成这组软上限变量或开放该配置；它是文稿可选扩展，不是已启用的正式求解项。** `waiting_only`关闭节拍项，`quadratic`使用节拍平方，是实验对照选项；后者不再是纯线性目标的MILP基线。

对应：`model.py`的`waits`、`rhythm`、`secondary_objective`；`run_experiments.py::solve`第二阶段分支。

## 9.5 执行输出的收尾与身份解码

两阶段结束后，可在保留产品完工时间和阶段二加权目标上界的条件下，固定全部非连续变量（这次包括`sync_`同步开关），最小化全部已建模动作、腔室周期及装载锁复位的最晚结束时刻$C_{\rm end}$。该收尾过程只调整连续时刻，完成后再按第3.3节恢复实际晶圆编号。

$C_{\rm end}$与产品$C_{\max}$是不同指标；末端辅助片归还或清洁可晚于最后一片产品回LP。保留阶段二加权和不增，不等于每个等待分项和节拍分项分别不增。当前收尾入口见`experiments/nondecreasing_review_20261102/review_experiments.py::refine`的`cleanup`分支，可显式指定新主实验的源批次。

# 10. 编码等价性、初始化与最优性判断

编码省略同属性产品的身份排列，但仍保留全Pjob的非递减取片和跨LP次序。只有在第3.4节的可互换前提下，才能与**具有相同非递减规则、同步取片条件及物理约束**的逐片模型比较：

$$
\min_{\xi\in\mathcal F}C_{\max}
=\min_{\xi\in\mathcal F_{\mathrm W}^{\rm seq}}C_{\max}.\tag{29}
$$

不能将右侧换成不受全Pjob顺序限制的旧逐片可行域，也不能换成禁止同Pjob同步取片的严格模型。解码按第3.3节的取片时刻及同刻排序规则映射到$\mathcal L_j$，同时检查来源LP、实际身份和完整路线。

初始化补全只使用已启用对和周期，以零目标求出辅助赋值；随后提升到完整候选域，执行原始约束检查和独立物理验解，才成为正式求解的初始可行解。零目标补全的“optimal”不证明排程完工时间最优。

以下状态须区分：有可行解的超时提供上界；无可行解的超时不能证明不可行；只有完整候选域的主目标界闭合才支持主问题最优；固定结构、限缩候选或第二阶段的最优结论均有相应范围。

## 10.1 与历史严格规则的结果边界

放宽出片规则后，历史严格排程仍满足新的顺序要求；在其他输入与物理约束相同时，它可以作为新模型的可行上界或共同起点。旧最优值和旧下界不能直接作为新模型的最优值和下界，旧求解时间、内存、成功率及方法排名也不能直接外推。

同理，固定主要结构但释放同步开关的精修问题可能扩大可行域，旧子问题最优值需要重新证明。固定全部离散选择、包括同步开关的历史收尾仍可作为该给定排程的后处理记录保留；对新的主阶段输出进行收尾则必须使用新的源批次。

本说明解释模型，不把代码检查通过当作实验完成。实际数值、覆盖范围和最优性状态须依据对应批次的冻结输入、完整赋值验解、独立物理重放及求解界判断。补跑入口与各组预算见[期刊实验命令](JOURNAL_EXPERIMENT_COMMANDS.md)和[学位论文实验命令](EXPERIMENT_COMMANDS.md)，具体证据采用当前主稿所引用的验证记录。

# 11. 历史串行构造在当前规则下的数量下界

本节解释历史构造记录 `gif/kexingyu/pjob_fifo_20261029/`。其中严格依次取片的串行排程仍满足当前非递减规则，因此其构造族仍可用于给出下界；它不枚举新增的同时取片排程，也不是对所有输入的统一计数。规定四LP各$a=N/4$片，Pjob1来自LP1仅可CH2，Pjob2来自LP2仅可CH3，Pjob3来自LP3/LP4可用两腔；同Pjob内部顺序固定，因此Pjob3先取完LP3再取LP4。

每产品使用一个完成回片和清洁的串行块，再进入下一块。三个固定内部顺序的任务链长度为$a,a,2a$，它们的交错数为$N!/(a!a!(2a)!)$；Pjob3的$2a$片各有两个腔室选择：

$$
L_{\rm FIFO}(N)=\frac{N!}{((N/4)!)^2(N/2)!}\,2^{N/2}.\tag{30}
$$

不同任务交错改变LP取片顺序，不同腔室选择改变VTR放片地点，故该构造不重复。每块间隔900秒，32片完整构造在100000秒时域内；每产品后清洁使其同时适用$H=3,10$，两次曝光保持连续。该构造族的大小是整个可行空间的下界，不是精确总数，也不是最优排程数。

| 产品数$N$ | 历史筛选后已列数 | 每固定配置已列 | 每固定配置下界 |
|---|---:|---:|---:|
| 8 | 6720 | 3360 | 6720 |
| 16 | 676 | 338 | 230630400 |
| 32 | 6 | 3 | 506980245130444800 |

已列数来自旧抽样记录筛选，不能用于比较空间大小。四配置为纯$4\times1$/$2\times2$与$H=3/10$。在本构造中两个阈值显示顺序相同应合并，两种配方不同，四配置并集下界为$2L_{\rm FIFO}(N)$，不能乘4。

此前仅按任务--LP分组时的下界为$L_{\rm old}=N!/((N/4)!)^4\cdot2^{N/2}$，两者关系为

$$
L_{\rm FIFO}(N)=\frac{L_{\rm old}(N)}{\binom{N/2}{N/4}}.\tag{31}
$$

被除去的是Pjob3中LP3和LP4任意交错的自由度。此关系只比较这两个构造族，不表示整个模型可行域缩小了同一倍数。若改资格、库存或缩紧时域/完工时间限制，须重新证明该下界。

# 12. 与文稿和代码的对应索引

下列路径均相对于 `JMS-version/`。代码位置以函数名为准，避免编辑后行号失效。

| 本说明 | 文稿公式标签或段落 | 实现位置 |
|---|---|---|
| 式(1)--(4) | `pjob-input-code`、`joint-membership`、`pjob-release-boundary`、`pjob-nondecreasing-pick` | `pjobs.py`、`pjob_order.py`、`joint_pairing_model.py` |
| 式(5)--(7) | `joint-chamber`、`pair-type`、`candidate-bounds` | 配对模块、`Integrated.__init__` |
| 式(8)--(10) | `cycle-capacity`、`cycle-products`、`cycle-exposures` | `add_chamber_cycles` |
| 式(11)--(17) | `operation-time`至`cycle-unload` | `event`、`route`、`accompaniment`、`chambers` |
| 式(18)--(19) | `clean-counter`、`clean-time` | 周期模块计数循环、`chambers` |
| 式(20)--(24) | `dummy-assign`至`residence`、紧凑互斥段 | `capacity`、`colored_nonoverlap`、`resources` |
| 式(25)--(28) | `primary-objective`至`secondary-objective` | `model.py`、`run_experiments.py::solve` |
| 式(29) | `model4-equivalence` | `encoding`、`decode_members`、`validate` |
| 式(30)--(31) | `model4-family-count`及历史串行构造下界说明 | `gif/kexingyu/pjob_fifo_20261029/manifest.json` |

文稿公式标签完整形式为 `eq:上述标签-cn`。除明确列出的对照构造器及历史构造记录外，上述代码均属于 `model4_pjob_nondecreasing_20261102/`。全文依据当前代码和中文主稿核对；本次仅更新说明、构建索引与文档入口，不修改求解实现、活动实验或既有排程证据。
