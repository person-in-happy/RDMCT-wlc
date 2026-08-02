# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[2]`
- Time limit: `1200.0 s` per run
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0 | 2400 | 7141 | 0.9226 | 5.729e+04 | 9165 | 1 [1, 1] |
| HEM | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.2402 | 2400 | 7156 | 0.9421 | 5.801e+04 | 9165 | 1 [1, 1] |
| HEM + Beam | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.1098 | 2400 | 7156 | 0.9401 | 5.787e+04 | 9165 | 1 [1, 1] |
| HEM + Structure | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.09429 | 2400 | 7156 | 0.9342 | 5.89e+04 | 9165 | 1 [1, 1] |
| Proposed | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.1034 | 2400 | 7156 | 0.9309 | 5.785e+04 | 9165 | 1 [1, 1] |
| 23D Features Only | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.09316 | 2400 | 7160 | 0.9313 | 5.792e+04 | 9165 | 1 [1, 1] |
| SCIP | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0 | 2400 | 7160 | 0.931 | 5.751e+04 | 9165 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 9 | 1/1 | 5 | 0.5556 | -0.4802 | 0.752 | 1 |
| HEM | 9 | 9 | 1/1 | 5 | 0.5556 | 0.494 | 0.3262 | 1 |
| HEM + Beam | 9 | 9 | 1/1 | 4 | 0.4444 | 0.2314 | 0.5898 | 1 |
| HEM + Structure | 9 | 9 | 1/1 | 5 | 0.5556 | 1.048 | 0.5449 | 1 |
| adaptive_cutsel | 9 | 9 | 1/1 | 3 | 0.3333 | -1.453 | 0.8984 | 1 |
| 23D Features Only | 9 | 9 | 1/1 | 3 | 0.3333 | 0.1801 | 0.5449 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 0.1029% | 9 | 0.0001384 | 0 | n/a% |
| HEM | 9 | 0% | 9 | 0.01123 | 0 | n/a% |
| HEM + Beam | 9 | 0% | 9 | 0.0092 | 0 | n/a% |
| HEM + Structure | 9 | 0% | 9 | 0.003327 | 0 | n/a% |
| adaptive_cutsel | 9 | -0.4386% | 9 | -0.008274 | 0 | n/a% |
| 23D Features Only | 9 | 0.1029% | 9 | 0.0004036 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.7778 | 0.2657% | 0.08012% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.5556 | -0.7215% | 0.07458% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.4444 | 0.2314% | -0.03486% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.5556 | 1.048% | 0.00593% |

## Interpretation guardrails

- Compare methods only on identical instance-seed pairs.
- Metric directions: solving time, PAR-2, best objective, gap, and PDI are all lower-is-better for these minimization models.
- Best objective measures incumbent quality; gap measures remaining certificate uncertainty; PDI measures anytime primal-dual progress; time is a speed claim only when solve outcomes are comparable.
- Mean node count is diagnostic, not a monotone quality metric: fewer nodes can mean an efficient tree or a stalled root relaxation.
- Report timeout-aware gap and primal-dual integral beside wall-clock time.
- `adaptive_cutsel` is the original four-parameter SCIP hybrid selector interface. It is the full learned ACS method only when `--acs_predictions` contains held-out predictions from a separately trained ACS model.
- `hem` requires a separately trained 13-feature checkpoint; using the 23-feature checkpoint would invalidate the ablation.
- `hem_beam` reuses the exact HEM checkpoint and changes only greedy to beam decoding.
- `hem_structure` reuses the exact Proposed checkpoint and structure reranking, changing only beam to greedy decoding.
- `a3c` and `beam_search` share the same independently trained flat-A3C checkpoint and differ only in greedy versus beam decoding.
- `proposed` uses the separately trained 23-feature role-submodular checkpoint; every method receives the same SCIP, memory, warm-start, instance, and solver-seed limits.
- Schedule wait and cadence metrics are observational in the benchmark; no method receives an extra postprocessing budget.
