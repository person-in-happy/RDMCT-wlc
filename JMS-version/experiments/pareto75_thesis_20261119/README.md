# 75片混合批次的双目标排程

本目录为学位论文第三个创新点的75片扩展。比较使用实际配置D的37片并行配方、38片链式配方和原有可行起点。算法与新结果均位于本目录。小规模实验和原模型以只读方式导入。

- [复核说明与三种子结果](review/review_CN.md)
- [75片全部发现前沿](review/front75.csv) · [按方法与种子评分](review/runs75.csv) · [前沿图](review/figures/pareto_75.png)
- [完整运行协议与指纹](results/formal02/protocol.json) · [原始运行目录](results/formal02) · [原模型赋值证书](results/formal02/row_audit)
- [论文所在目录](D:/git/git/硕士毕设/论文初稿_20261110) · [可阅读的学位论文](D:/git/git/硕士毕设/论文初稿_20261110/main.pdf)

## 从代码到排程

请在可见前台终端使用项目现有的Python环境。本项目复用了原模型的PySCIPOpt、已有的SciPy/HiGHS和Matplotlib。从本目录运行以下命令，求解器的并发和单线程设置由冻结协议记录。

```powershell
G:/conda/envs/a3cenv/python.exe -B -X utf8 -u campaign75.py
G:/conda/envs/a3cenv/python.exe -B -X utf8 -u complete_front.py
G:/conda/envs/a3cenv/python.exe -B -X utf8 -u review.py small
G:/conda/envs/a3cenv/python.exe -B -X utf8 -u review.py
G:/conda/envs/a3cenv/python.exe -B -X utf8 -u figures.py
```

已完成的单元可以按协议指纹续读。独立的新运行应使用本目录的独立副本并采用新的空输出目录，保留本次原始证据。小规模复核读取原有的164组归档。75片最终复核覆盖所有提交点及所有运行合并后的非支配点。搜索阶段取得的目标坐标与见证恢复、完整验解的时间分别保存。排程JSON中记录晶圆身份、取放与回片时刻、周期和清洁，逐行证书按同一动作表的SHA-256索引。

`large75.py`接入既有的对内动作和重定时模型。领域搜索联合改变生产块、分腔、配对及取放次序。NSGA-II与MOEA/D以同一编码和解码器评估，固定结构对照只调节时刻。完整模型只参与事后可行性检查。学位论文排版与数值复核入口分别为`manuscript.py`和`review.py`，原稿快照保存在`manuscript_backup`。
