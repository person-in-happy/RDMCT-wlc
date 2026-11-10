# Pjob批次内编码与全局严格出片MILP

本目录保留历史严格取片模型，规则与证据归属见[当时的编码审查](../revisions/20261029_pjob_index_encoding/REVIEW_CN.md)。[当前模型公式说明](../MODEL_EXPLANATION_CN.md)采用后续非递减规则，不能与本目录逐项混用。原代码与冻结批次保留供复现。

输入产品先按工艺模式、腔室资格分组，再按实际晶圆全局编号生成 `Pjob_j[k]`。编号表同时保留实际ID及来源LP；同批次两片产品不得同时从LP取出。

- `pjob_order.py`：输入编码、相邻非空LP的连续时间分界、同Pjob取片同步限制、最终全局序号解码与顺序重放检查。
- `model.py`：保留库存选择、PW对、工艺周期与完整资源模型，接入新增顺序约束。
- `seed.py`：按批次内连续区段分腔，构造满足统一出片顺序的起点。
- `validate.py`：检查实际晶圆、编码、来源LP及严格取片顺序；原物理检查保持执行。

同一Pjob仍可拆分至多个PW对和腔室。不同Pjob可交错出片，资格有交集且模式相容时可以组对；后续加工与回片不要求全路线FIFO。辅助晶圆实体仍作为可复用资源。

设非空Pjob数为J、非空Pjob--LP组数为G、产品数为N，产品库存选择块为2GN；跨LP顺序增加G-J个连续辅助量。禁止同批同步取片使用已有同步选择变量，不增加产品身份排列变量。

输出保留 `events/pairs/cycles/jobs` 格式，增加 `product_encoding` 及每片产品的 `pjob_index`、`encoded_product`、`wafer_number`。`model_scope` 为 `pjob_global_fifo_v2`。最终输出按全Pjob取片次序解码；求解阶段中的物理验解使用相同映射。

29项正确性测试通过，包含完整模型赋值检查、两阶段输出、跨LP逆序/同时取片拒绝以及跨Pjob同步取片保留。它们是开发验证，不计入文稿实验次数。

历史批次入口为本目录 `run_experiments.ps1`；`paper` 102次、`qualification` 6次、`rhythm` 48次及 `paper_cuts` 72次属于当时的严格取片协议。恢复已有批次时使用原冻结配置。当前补充实验见[期刊命令](../JOURNAL_EXPERIMENT_COMMANDS.md)，不得用本目录结果替代当前模型比较。
