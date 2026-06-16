# Ablation Results

## Setup

- Instance directory: `G:\git\RDMCT-A3C\generated_instances\MIP_pipeline_demo_ablation`
- Instance files: `mip_ablation_demo_20260613.lp`
- Model path: `G:\git\RDMCT-A3C\data\mip_20260611\_mip_wafer11_41_train_20260611.lp_petri_transfer\_mip_wafer11_41_train_20260611.lp_petri_transfer_2026_06_11_10_22_47_0000--s-1\params.pkl`
- Generated MIP: `G:\git\RDMCT-A3C\generated_instances\MIP_pipeline_demo_ablation\mip_ablation_demo_20260613.lp`
- Model description: `G:\git\RDMCT-A3C\generated_instances\MIP_pipeline_demo_ablation\mip_ablation_demo_20260613_model.md`
- Comparison SVG: `G:\git\RDMCT-A3C\ablation_results\ablation_petri_transfer_20260613_170345_comparison.svg`
- Gantt directory: `G:\git\RDMCT-A3C\ablation_results\ablation_petri_transfer_20260613_170345_gantt`

## Summary

| Method | Completed | With Incumbent | Solved | Mean Time | Mean Incumbent Time | Mean Nodes | Mean Best Obj | Mean Gap | Mean Nonzero Vars |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| solver_only | 1/1 | 1/1 | 0/1 | 1,800.00 | 1,800.00 | 93,115.00 | 820.75 | 25.361 | 2,515.00 |
| a3c_only | 1/1 | 1/1 | 0/1 | 1,800.00 | 1,800.00 | 22,521.00 | 725.63 | 22.399 | 1,505.00 |
| beam_only | 1/1 | 1/1 | 0/1 | 1,800.00 | 1,800.00 | 32,842.00 | 812.21 | 25.191 | 3,429.00 |
| a3c_beam | 1/1 | 0/1 | 0/1 | 1,800.00 | n/a | 23,832.00 | n/a | n/a | n/a |

## Diagnostics

- The run covers fewer than 3 instances, so method differences are not statistically meaningful.

## Per-Instance Results

| Method | Instance | Status | Time | Best Obj | Nodes | Gap | Solutions | Incumbent | Comparable | Nonzero Vars | Error |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| solver_only | mip_ablation_demo_20260613.lp | timelimit | 1,800.00 | 820.75 | 93,115.00 | 25.361 | 14 | True | True | 2515 | None |
| a3c_only | mip_ablation_demo_20260613.lp | timelimit | 1,800.00 | 725.63 | 22,521.00 | 22.399 | 9 | True | True | 1505 | None |
| beam_only | mip_ablation_demo_20260613.lp | timelimit | 1,800.00 | 812.21 | 32,842.00 | 25.191 | 52 | True | True | 3429 | None |
| a3c_beam | mip_ablation_demo_20260613.lp | timelimit | 1,800.00 | n/a | 23,832.00 | 100,000,000,000,000,000,000.00 | 0 | False | False | 0 | None |

## Hyperparameters

### solver_only

- `method`: `solver_only`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `1800.0`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `post_process_wait_penalty`: `0.05`
- `chamber_idle_square_penalty`: `1e-05`
- `chamber_idle_penalty`: `0.0001`
- `solver`: `SCIP default cut selection`

### a3c_only

- `method`: `a3c_only`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `1800.0`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `post_process_wait_penalty`: `0.05`
- `chamber_idle_square_penalty`: `1e-05`
- `chamber_idle_penalty`: `0.0001`
- `decode_type`: `greedy`
- `model_path`: `G:\git\RDMCT-A3C\data\mip_20260611\_mip_wafer11_41_train_20260611.lp_petri_transfer\_mip_wafer11_41_train_20260611.lp_petri_transfer_2026_06_11_10_22_47_0000--s-1\params.pkl`
- `beam_size`: `3`
- `use_cutsel_percent_policy`: `True`

### beam_only

- `method`: `beam_only`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `1800.0`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `post_process_wait_penalty`: `0.05`
- `chamber_idle_square_penalty`: `1e-05`
- `chamber_idle_penalty`: `0.0001`
- `decode_type`: `heuristic_beam`
- `heuristic_beam_size`: `3`
- `heuristic_redundancy_weight`: `0.15`
- `heuristic_max_candidates`: `256`
- `heuristic_max_selected_cuts`: `256`
- `score_weights`: `{'obj_parallelism': 0.15, 'efficacy': 0.35, 'support_penalty': 0.1, 'integral_support': 0.15, 'violation': 0.25}`

### a3c_beam

- `method`: `a3c_beam`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `1800.0`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `post_process_wait_penalty`: `0.05`
- `chamber_idle_square_penalty`: `1e-05`
- `chamber_idle_penalty`: `0.0001`
- `decode_type`: `beam_search`
- `model_path`: `G:\git\RDMCT-A3C\data\mip_20260611\_mip_wafer11_41_train_20260611.lp_petri_transfer\_mip_wafer11_41_train_20260611.lp_petri_transfer_2026_06_11_10_22_47_0000--s-1\params.pkl`
- `beam_size`: `3`
- `use_cutsel_percent_policy`: `True`

## Solutions

Full variable assignments are stored in the JSON output.
