# 实验批次全索引（2026-11-08）

由 `catalog.py` 只读生成。状态来自保存的汇总/逐单元结果；不是本次重新验解。目录推断已注明。计数为运行记录，不能当作独立实例数。汇总行可能包括待跑单元或参考检查，不能直接当作求解次数；valid=true为保存的检查标记，0也可能表示缺少该字段。没有汇总不代表没有结果；见 inventory.json 的文件索引。

| 模型 | 批次（JMS-version/results/） | 汇总行数 | 状态计数 | 保存的 valid=true |
|---|---|---:|---|---:|
| unclassified / support | `.default_gap_queue` | 0 | {} | 0 |
| unclassified / support | `command_entry_tests` | 0 | {} | 0 |
| M4-D | `current_defaults_crossover_20261104_163238` | 216 | {"timelimit": 192, "memlimit": 24} | 0 |
| M4-D | `current_defaults_cuts_20261104_100149` | 72 | {"timelimit": 72} | 9 |
| M4-D | `current_defaults_gantt_20261103_222109` | 4 | {"timelimit": 4} | 0 |
| M4-D | `current_defaults_paper_20261104_075634` | 24 | {"timelimit": 24} | 3 |
| M4-D | `current_defaults_scale32_20261105_110904` | 0 | {} | 0 |
| M4-D | `current_defaults_scale32_20261105_112002` | 0 | {} | 0 |
| M4-D | `current_defaults_scale32_20261105_112327` | 9 | {"timelimit": 3, "memlimit": 6} | 0 |
| M4-D | `current_defaults_small_prepared_20261103` | 8 | {"optimal": 4, "timelimit": 4} | 5 |
| unclassified / support | `frozen_models_20260906` | 0 | {} | 0 |
| M4-D | `gap_d_encoding_20261108_r1` | 24 | {"failed": 1, "pending": 23} | 0 |
| M4-D | `gap_d_encoding_20261108_r2` | 24 | {"optimal": 12, "timelimit": 12} | 24 |
| M4-D | `gap_d_structure_20261108_r1` | 36 | {"optimal": 1, "pending": 35} | 1 |
| M4-D | `gap_entrycheck_encoding_20261108` | 0 | {} | 0 |
| unclassified / support | `gap_entrychecks_20261108_v2` | 0 | {} | 0 |
| M4-D | `gap_queuecheck_20261108` | 2 | {"mock_queue_complete": 2} | 0 |
| M3 | `heterogeneous100_80_180_90_20261022` | 0 | {} | 0 |
| M2 historical (subcampaigns differ) | `joint_model` | 0 | {} | 0 |
| M2 historical (subcampaigns differ) | `joint_model_reuse` | 0 | {} | 0 |
| M2 historical (subcampaigns differ) | `joint_model_validation` | 0 | {} | 0 |
| M4-group | `model4_ablation_all_20261028_164314` | 216 | {"feasible_limit": 216} | 216 |
| M4-group | `model4_core_all_20261028_091756` | 0 | {} | 0 |
| M4-group | `model4_core_all_20261028_fix1` | 126 | {"feasible_limit": 105, "optimal": 9, "no_incumbent_timelimit": 12} | 114 |
| M4-group | `model4_crossover_all_20261029_080528` | 216 | {"feasible_limit": 216} | 216 |
| M4-E | `nondecreasing_followup_exact_20261102_205212` | 24 | {"reference_checked": 8, "optimal": 5, "timelimit": 11} | 24 |
| M4-E | `nondecreasing_followup_timing_20261103_142541` | 72 | {"checked_without_optimization": 72} | 72 |
| M4-E | `nondecreasing_review_baseline_20261103_112023` | 36 | {"complete": 36} | 36 |
| M4-E | `nondecreasing_review_rhythm_20261103_135933` | 24 | {"complete": 24} | 24 |
| M4-E | `nondecreasing_strengthen_representation_20261103_075856` | 36 | {"complete": 36} | 36 |
| M4-E | `nondecreasing_strengthen_rhythm_memory_20261103_141315` | 12 | {"complete": 12} | 12 |
| M2 (directory inference) | `optimality_work_20261021` | 0 | {} | 0 |
| M2 (directory inference) | `optimality_work_20261022` | 0 | {} | 0 |
| M2 | `optional_cleaning_20261016_core` | 126 | {"feasible_limit": 108, "optimal": 4, "no_incumbent_timelimit": 12, "execution_failed": 2} | 112 |
| M2 | `optional_cleaning_20261016_crossover` | 216 | {"feasible_limit": 192, "execution_failed": 24} | 192 |
| M2 | `optional_cleaning_20261016_smoke` | 5 | {"feasible_limit": 4, "optimal": 1} | 5 |
| M2 | `optional_cleaning_ablation_6gb_p2` | 216 | {"feasible_limit": 216} | 216 |
| M2 | `optional_cleaning_doe_n8n16_remaining_20261020_14gb_p1` | 72 | {"feasible_limit": 72} | 72 |
| M2 | `optional_cleaning_scale_n32_20261020_14gb_p1` | 9 | {"feasible_limit": 3, "execution_failed": 6} | 3 |
| M2 | `optional_cleaning_sensitivity_6gb_p2` | 96 | {"feasible_limit": 90, "execution_failed": 6} | 90 |
| M2 | `optional_cleaning_sensitivity_seedfix_20261020_6gb_p2` | 6 | {"feasible_limit": 6} | 6 |
| M2 (directory inference) | `paper_cpsat_optimality_20261022` | 0 | {} | 0 |
| M2 | `paper_gantt_n16_optimal_attempt_20261020` | 4 | {"feasible_limit": 4} | 4 |
| M2 (directory inference) | `paper_optimality_foreground_20261022` | 0 | {} | 0 |
| M4-FIFO | `pjob_fifo_crossover_all_20261030_190540` | 216 | {"feasible_limit": 216} | 216 |
| M4-FIFO | `pjob_fifo_paper_all_20261030_075555` | 102 | {"feasible_limit": 84, "no_incumbent_timelimit": 12, "optimal": 6} | 90 |
| M4-FIFO | `pjob_fifo_paper_cuts_all_20261030_144535` | 72 | {"feasible_limit": 72} | 72 |
| M4-FIFO | `pjob_fifo_qualification_all_20261030_120650` | 6 | {"feasible_limit": 6} | 6 |
| M4-FIFO | `pjob_fifo_rhythm_all_20261030_124059` | 48 | {"feasible_limit": 48} | 48 |
| M4-FIFO | `pjob_fifo_scale32_all_20261031_174246` | 9 | {"feasible_limit": 6, "execution_failed": 3} | 6 |
| M4-FIFO | `pjob_fifo_scale32_memory_retry_20261031_01` | 3 | {"feasible_limit": 3} | 3 |
| M4-E | `pjob_nondecreasing_crossover_all_20261103_192951` | 0 | {} | 0 |
| M4-E | `pjob_nondecreasing_paper_all_20261102_231102` | 102 | {"feasible_limit": 84, "no_incumbent_timelimit": 12, "optimal": 6} | 90 |
| M4-E | `pjob_nondecreasing_paper_cuts_all_20261103_151135` | 72 | {"feasible_limit": 72} | 72 |
| M4-E | `pjob_nondecreasing_qualification_all_20261103_032308` | 6 | {"feasible_limit": 6} | 6 |
| M4-E | `pjob_nondecreasing_rhythm_all_20261103_033856` | 48 | {"feasible_limit": 48} | 48 |
| M4-E | `pjob_nondecreasing_scale32_all_20261103_192953` | 0 | {} | 0 |
| M4-FIFO | `review_baseline_20261101_104429` | 36 | {"complete": 36} | 36 |
| M4-FIFO | `review_cleanup_20261101_103259` | 42 | {"complete": 42} | 42 |
| M4-FIFO | `review_cleanup_entrycheck_20261101_01` | 0 | {} | 0 |
| M4-D | `review_d_crossover_20261105_r1` | 216 | {"timelimit": 192, "memlimit": 24} | 0 |
| M4-D | `review_d_cuts_20261105_r1` | 72 | {"timelimit": 72} | 9 |
| M4-D | `review_d_scale32_20261105_r1` | 9 | {"timelimit": 3, "execution_failed": 1, "pending": 5} | 0 |
| M4-D | `review_d_scale32_remaining_20261107_r2` | 6 | {"memlimit": 6} | 0 |
| M4-FIFO | `review_followup_exact_20261102_01` | 18 | {"reference_checked": 6, "optimal": 3, "timelimit": 9} | 18 |
| M4-FIFO | `review_followup_parallel_20261102_01` | 3 | {"optimal": 1, "timelimit": 2} | 1 |
| M4-FIFO | `review_followup_residency_20261102_01` | 6 | {"optimal": 5, "infeasible": 1} | 5 |
| M4-FIFO | `review_followup_timing_20261102_01` | 72 | {"checked_without_optimization": 72} | 72 |
| M4-FIFO | `review_rhythm_20261101_133022` | 36 | {"complete": 36} | 36 |
| M4-FIFO | `review_rhythm_entrycheck_20261101_01` | 12 | {"pending": 12} | 0 |
| M4-FIFO | `strengthen_representation_20261101_162725` | 36 | {"complete": 36} | 36 |
| M4-FIFO | `strengthen_representation_entrycheck_20261101_01` | 12 | {"pending": 12} | 0 |
| M4-FIFO | `strengthen_rhythm_entrycheck_20261101_01` | 4 | {"pending": 4} | 0 |
| M4-FIFO | `strengthen_rhythm_memory_20261101_161209` | 12 | {"complete": 12} | 12 |
| M2 | `supp_cleaning_20261021_6gb_p2` | 96 | {"feasible_limit": 96} | 96 |
| M2 | `supp_doe_auto_v1` | 0 | {} | 0 |
| M2-lowmem | `supp_doe_lowmem_20261026_p1` | 180 | {"feasible_limit": 162, "execution_failed": 18} | 162 |
| M2 | `supp_fixed_20261021_6gb_p2` | 12 | {"feasible_limit": 6, "optimal": 4, "execution_failed": 2} | 10 |
| M2 | `supp_fixed_checkfix_20261022_6gb_p2` | 2 | {"optimal": 2} | 2 |
| M2 | `supp_fixed_repeat_20261022_6gb_p2` | 12 | {"feasible_limit": 6, "optimal": 6} | 12 |
| M2 | `supp_gantt16_auto_v1` | 4 | {"feasible_limit": 4} | 4 |
| M2 | `supp_mode24_20261021_24gb_p1` | 0 | {} | 0 |
| M2 | `supp_mode24_20261023_auto_p1` | 0 | {} | 0 |
| M2 | `supp_mode24_auto_v2` | 0 | {} | 0 |
| M2-compact | `supp_mode24_compact_20261026_p1` | 72 | {"feasible_limit": 28, "pending": 44} | 28 |
| M2 | `supp_mode24_fixed16384_20261024_p1` | 0 | {} | 0 |
| M2-lowmem | `supp_mode24_lowmem_20261026_p1` | 45 | {"feasible_limit": 45} | 45 |
| M2 | `supp_mode24_resource_v3` | 0 | {} | 0 |
| M2 | `supp_ood_auto_v1` | 0 | {} | 0 |
| M2 | `supp_rhythm_20261021_6gb_p2` | 48 | {"feasible_limit": 48} | 48 |
| M2 | `supp_scale32_auto_v1` | 0 | {} | 0 |
| M2-lowmem | `supp_scale32_lowmem_20261026_p1` | 9 | {"feasible_limit": 6, "execution_failed": 3} | 6 |
| M1 historical fixed structure | `wafer50_gantt` | 0 | {} | 0 |
| M1 historical fixed structure | `wafer_multiscale_gantt` | 0 | {} | 0 |

## CIE原始CSV与保存审计核对

| 阶段 | 计划 | 保存审计行数 | 本次实际CSV行数 | incumbent | 审计通过 |
|---|---:|---:|---:|---:|---|
| doe | 300 | 300 | 300 | 300 | True |
| main | 2700 | 2700 | 2700 | 2700 | True |
| ood | 729 | 729 | 729 | 729 | True |
| sensitivity | 80 | 80 | 80 | 80 | True |
| spbs | 960 | 960 | 960 | 728 | True |
| stability | 1500 | 1500 | 1500 | 1500 | True |
| validation | 4 | 4 | 4 | 4 | True |
