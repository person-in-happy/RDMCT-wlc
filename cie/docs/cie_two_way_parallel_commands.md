# 历史归档：旧两路并行命令

> 本文不定义当前正式协议。

两路或多路并行只是一种执行方式。当前规则见 [`../README.md`](../README.md)：

- 相同 `CampaignId`；
- 不同 `ShardTag` 和 `LogId`；
- solver seeds 互不重叠；
- training seeds、LP、模型、ACS、time、memory 和代码完全相同；
- 记录 GPU/RAM 竞争；wall-clock 比较优先使用单路或独占设备。

完整性以合并后的预期行数和实例级统计为准。
