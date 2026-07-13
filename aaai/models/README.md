# 模型目录

- `hem/`：13 维通用特征 HEM checkpoint；
- `proposed/`：23 维结构感知方法 checkpoint。

训练脚本会创建带时间戳的子目录。正式实验入口会自动寻找各目录最新的 `params.pkl`，也可以手动用 `-HemModel` 和 `-ProposedModel` 指定。
