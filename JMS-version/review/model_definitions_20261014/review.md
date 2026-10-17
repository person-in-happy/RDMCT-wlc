# 建模定义复核（2026-10-14）

对象：`JMS-version/JMS_Review_CN.tex`。修改前完整备份：`JMS_Review_CN.before.tex`。

已确认：

- `joint_chamber_cycle_model.py:65-92` 和 `JMS-version/joint_model/validate.py:146-155` 均采用 H 阈值；H-1 后提前清洁仅允许紧接 2x2 周期；达到 H 的末段必须清洁。
- `JMS-version/joint_model/model.py:60-93` 采用 T=N_zeta+2*N_psi、Jmax=floor(T/(H-1))、Pmax=N+T+2*Jmax、Qmax=T+Jmax。
- 原文“每次清洁前有 H-1 个周期”“清洁次数为 Jmax”“Qmax 个生产周期”不准确，已改为带条件的清洁规则、清洁次数上界和含清洁的候选周期容量。
- N 已在正文及参数表单列定义；Pmax 已补充候选启用、三项推导、辅助复用及数值例子。

范围：仅修订当前中文文稿的定义与解释，不修改模型、实验记录、检查点或其他稿件。

待补实验依据：本次定义澄清无新增实验依赖；已有未完成实验仍按原状态处理。

编译与版面检查：三轮 XeLaTeX 编译成功，共 20 页；无 Overfull、未解析引用、超大浮动体或缺字警告。已渲染并人工检查第 3、4、5、11 页，容量推导、参数表、清洁约束解释及实验中的 H 定义均显示完整，无遮挡或越界。构建结果及源文件 SHA-256 见 `build_report.json`。中文 PDF 更新于 `JMS-version/JMS_Review_CN.pdf` 和 `JMS-version/output/pdf/JMS_Review_CN.pdf`。
