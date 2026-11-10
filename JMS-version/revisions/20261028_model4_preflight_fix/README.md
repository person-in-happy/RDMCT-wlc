# 模型4预检失败修复（2026-10-28）

用户运行`core`时，在`n8_H3_4x1_dual`的参考补全阶段遇到`given constraint is not ExprCons but bool`。失败批次`../../results/model4_core_all_20261028_091756/`、原始日志及冻结代码均保留。

## 原因与修改

纯4×1整载参考不需要辅助对，未达到清洁阈值时也没有清洁周期。参考补全使用的缩减子模型因此没有清洁候选，其清洁变量为常数0。原实现把`0 >= 0`、`0 == 0`等表达式直接交给SCIP，Python先将其求值为布尔值，从而在建模阶段报错；这不构成不可行证明。

- `joint_chamber_cycle_model.py`：不存在清洁候选时跳过仅约束清洁的恒真式，保留计数器上下界、阈值及周期衔接约束。
- `model.py`：清洁总数改用`scip.quicksum`，即使各项都是0也生成SCIP表达式。
- `test_model4.py`：增加8片纯4×1、串行/均衡分腔、首周期/后继周期的回归，检查参考补全、完整原始约束、独立物理验解和Cmax保留。

正式搜索仍使用完整候选集合。完整模型允许清洁，相关规则没有删除。修复前已完成的9份参考证书对应的完整模型维度与修复后相同。具体修改见`model_fix.patch`，原始两个模型文件位于`original/`。

## 验证记录

- 修复前，两个新增测试均复现相同错误：`../20261027_model4/backend_validation_20261028_preflight_before_fix/`。
- 修复后，全部18项测试通过，用时24.55秒：`../20261027_model4/backend_validation_20261028_preflight_fix/`。
- 实际`core`入口完整预检13种配置通过，共14份参考证书（含分区辅助片对照），用时158.35秒。记录为`preflight_console.log`、`preflight_status.json`和新批次的`preflight_passed.json`。
- 新旧批次的实例哈希、126个实验单元、冻结策略和资源/时间预算一致；运行资产仅两个修复文件变化。核对记录及哈希见`verification.json`。

这是初始化与约束验证，不是126项主实验的性能结果。主实验尚未启动，可从仓库根目录继续已通过预检的新批次：

```powershell
powershell -ExecutionPolicy Bypass -File .\JMS-version\model4_pjob_20261027\run_experiments.ps1 -Action resume -Campaign JMS-version/results/model4_core_all_20261028_fix1
```

不要对旧失败批次直接`resume`，因为它冻结的是修复前源码。若后续又修改运行源码或预算，应另建新批次。
