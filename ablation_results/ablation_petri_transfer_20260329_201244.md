# Ablation Results

## Setup

- Instance directory: `G:\git\L2O-HEM-Torch\generated_instances\petri`
- Instance files: `petri_batch10_v3_20260329.lp`
- Model path: `G:\git\L2O-HEM-Torch\data\petri_mip_rl_beam_petri_batch10_v3_20260329.lp_petri_transfer\petri_mip_rl_beam_petri_batch10_v3_20260329.lp_petri_transfer_2026_03_29_19_07_03_0000--s-1\params.pkl`
- Generated MIP: `G:\git\L2O-HEM-Torch\generated_instances\petri\petri_batch10_v3_20260329.lp`
- Model description: `G:\git\L2O-HEM-Torch\generated_instances\petri\petri_batch10_v3_20260329_model.md`
- Comparison SVG: `G:\git\L2O-HEM-Torch\ablation_results\ablation_petri_transfer_20260329_201244_comparison.svg`
- Gantt directory: `G:\git\L2O-HEM-Torch\ablation_results\ablation_petri_transfer_20260329_201244_gantt`

## Summary

| Method | Mean Time | Mean Nodes | Mean Best Obj | Mean Gap | Mean Nonzero Vars | Valid Runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| solver_only | 2.000 | 1,250.00 | 750.00 | 0.0000 | 182.00 | 1/1 |
| a3c_only | 1.000 | 1,890.00 | 750.00 | 0.0000 | 182.00 | 1/1 |
| beam_only | 2.000 | 827.00 | 750.00 | 0.0000 | 183.00 | 1/1 |
| a3c_beam | 2.000 | 1,890.00 | 750.00 | 0.0000 | 182.00 | 1/1 |

## Per-Instance Results

| Method | Instance | Status | Time | Best Obj | Nodes | Gap | Nonzero Vars | Error |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| solver_only | petri_batch10_v3_20260329.lp | optimal | 2.000 | 750.00 | 1,250.00 | 0.0000 | 182 | None |
| a3c_only | petri_batch10_v3_20260329.lp | optimal | 1.000 | 750.00 | 1,890.00 | 0.0000 | 182 | None |
| beam_only | petri_batch10_v3_20260329.lp | optimal | 2.000 | 750.00 | 827.00 | 0.0000 | 183 | None |
| a3c_beam | petri_batch10_v3_20260329.lp | optimal | 2.000 | 750.00 | 1,890.00 | 0.0000 | 182 | None |

## Hyperparameters

### solver_only

- `method`: `solver_only`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `300`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `solver`: `SCIP default cut selection`

### a3c_only

- `method`: `a3c_only`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `300`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `decode_type`: `greedy`
- `model_path`: `G:\git\L2O-HEM-Torch\data\petri_mip_rl_beam_petri_batch10_v3_20260329.lp_petri_transfer\petri_mip_rl_beam_petri_batch10_v3_20260329.lp_petri_transfer_2026_03_29_19_07_03_0000--s-1\params.pkl`
- `beam_size`: `3`
- `use_cutsel_percent_policy`: `True`

### beam_only

- `method`: `beam_only`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `300`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `decode_type`: `heuristic_beam`
- `heuristic_beam_size`: `3`
- `heuristic_redundancy_weight`: `0.15`
- `score_weights`: `{'obj_parallelism': 0.15, 'efficacy': 0.35, 'support_penalty': 0.1, 'integral_support': 0.15, 'violation': 0.25}`

### a3c_beam

- `method`: `a3c_beam`
- `seed`: `1`
- `scip_seed`: `1`
- `scip_time_limit`: `300`
- `presolving`: `True`
- `separating`: `True`
- `conflict`: `True`
- `heuristics`: `True`
- `sel_cuts_percent`: `0.2`
- `policy_type`: `with_token`
- `decode_type`: `beam_search`
- `model_path`: `G:\git\L2O-HEM-Torch\data\petri_mip_rl_beam_petri_batch10_v3_20260329.lp_petri_transfer\petri_mip_rl_beam_petri_batch10_v3_20260329.lp_petri_transfer_2026_03_29_19_07_03_0000--s-1\params.pkl`
- `beam_size`: `3`
- `use_cutsel_percent_policy`: `True`

## Solutions

Full variable assignments are stored in the JSON output.
