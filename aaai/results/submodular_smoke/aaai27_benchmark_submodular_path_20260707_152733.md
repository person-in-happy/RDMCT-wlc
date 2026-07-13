# AAAI-27 Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, rdmct_feature_only, rdmct_a3c`
- Seeds: `[1]`
- Time limit: `5.0 s` per run
- Instances: `1`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Family | Scale | Runs | Inc. | Opt. | Time mean±std | Shifted GM | Gap | PDI | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rdmct_a3c | quick_petri | dual_source_cluster_tool | smoke | 1 | 1 | 0 | 5±0 | 5 | 0.2301 | 418.7 | 1 [1, 1] |
| rdmct_feature_only | quick_petri | dual_source_cluster_tool | smoke | 1 | 1 | 0 | 5±0 | 5 | 0.05394 | 405.1 | 1 [1, 1] |
| scip_default | quick_petri | dual_source_cluster_tool | smoke | 1 | 0 | 0 | 5±0 | 5 | n/a | n/a | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, and Holm-adjusted p<0.05.

| Proposed vs. | Pairs | Wins | Ties | Win rate | Mean PDI improvement | Median PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| scip_default | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a |
| adaptive_cutsel | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a |
| hem | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a |
| rdmct_feature_only | 1 | 0 | 0 | 0 | -3.354 | -3.354 | n/a | n/a |

## Interpretation guardrails

- Compare methods only on identical instance–seed pairs.
- Report timeout-aware gap and primal-dual integral beside wall-clock time.
- `adaptive_cutsel` is the original four-parameter SCIP hybrid selector interface. It is the full learned ACS method only when `--acs_predictions` contains held-out predictions from a separately trained ACS model.
- `hem` requires a separately trained 13-feature checkpoint; using the 23-feature checkpoint would invalidate the ablation.
