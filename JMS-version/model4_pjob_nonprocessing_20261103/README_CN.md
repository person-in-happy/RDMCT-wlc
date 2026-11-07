# 当前默认参数的独立后端

唯一推荐批次入口为 `paper_defaults.py`，详见上级 `CURRENT_DEFAULTS_RERUN_AND_GANTT_CN.md`。本目录从20261102非递减后端独立复制，旧目录和冻结批次未改。

- 工艺腔驻留扣除生产/清洁必要处理时间，默认100 s。
- AL与LL仍限制整个放片结束至取片开始区间；机械手限制完整承片区间，默认均100 s。
- 统一时域10000 s，包含LL复位尾部。时间条件大M取时域加必要间隔上界。
- 新输出模型标记为 `pjob_nondecreasing_nonprocessing_v1`。
- 主排程保留完整候选容量。不自动使用旧的串行构造器或旧固定结构比较入口；当前紧驻留参数不保证其构造排程可行。
- `paper_defaults.py inspect`只检查矩阵；`prepare`只冻结配置/已有合格起点；`run`才启动正式实验。
- `run_experiments.py`是低层求解实现；其他复制的实验入口是依赖文件，不代表其旧参考准备流程已适配当前100 s约束。

验证记录位于 `../revisions/20261103_results_default_residency/`。本轮未运行正式优化。
