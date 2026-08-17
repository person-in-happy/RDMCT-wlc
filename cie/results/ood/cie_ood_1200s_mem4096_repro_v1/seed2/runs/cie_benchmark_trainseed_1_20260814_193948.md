# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[2]`
- Time limit: `1200.0 s` per run
- Schedule-stability profile: `full`
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.9158 | 1141 | 0 | 2400 | 9325 | 1.561 | 7.029e+04 | 780.2 | 1 [0.9997, 1] |
| HEM | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.682 | 1141 | 0.1144 | 2400 | 9325 | 1.566 | 7.025e+04 | 780.2 | 1 [0.9998, 1] |
| HEM + Beam | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6963 | 1141 | 0.1062 | 2400 | 9325 | 1.566 | 7.025e+04 | 780.2 | 0.9999 [0.9997, 1] |
| HEM + Structure | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.7102 | 1141 | 0.05273 | 2400 | 9325 | 1.559 | 7.116e+04 | 780.2 | 0.9999 [0.9996, 1] |
| Proposed | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6458 | 1141 | 0.05477 | 2400 | 9990 | 1.782 | 7.445e+04 | 780.2 | 0.9999 [0.9997, 1] |
| 23D Features Only | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.5788 | 1141 | 0.07472 | 2400 | 9325 | 1.561 | 7.019e+04 | 780.2 | 0.9999 [0.9997, 1] |
| SCIP | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6047 | 1141 | 0 | 2400 | 9325 | 1.556 | 7.22e+04 | 780.2 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 9 | 1/1 | 2 | 0.2222 | -3.403 | 0.875 | 1 |
| HEM | 9 | 9 | 1/1 | 2 | 0.2222 | -8.812 | 0.9453 | 1 |
| HEM + Beam | 9 | 9 | 1/1 | 2 | 0.2222 | -8.82 | 0.9453 | 1 |
| HEM + Structure | 9 | 9 | 1/1 | 4 | 0.4444 | -6.14 | 0.6289 | 1 |
| adaptive_cutsel | 9 | 9 | 1/1 | 4 | 0.4444 | -8.653 | 0.752 | 1 |
| 23D Features Only | 9 | 9 | 1/1 | 2 | 0.2222 | -9.259 | 0.9258 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | -14.73% | 9 | -0.2258 | 0 | n/a% |
| HEM | 9 | -14.73% | 9 | -0.2159 | 0 | n/a% |
| HEM + Beam | 9 | -14.73% | 9 | -0.2156 | 0 | n/a% |
| HEM + Structure | 9 | -14.73% | 9 | -0.2228 | 0 | n/a% |
| adaptive_cutsel | 9 | -14.73% | 9 | -0.2208 | 0 | n/a% |
| 23D Features Only | 9 | -14.73% | 9 | -0.2214 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.3333 | 0.007777% | -0.0001852% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.2222 | -1.862% | -0.6082% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.2222 | -8.82% | -0.004673% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.4444 | -6.14% | 0% |

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
