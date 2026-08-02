# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 231.3+/-284.2 | 231.5 | 0 | 441.4 | 2218 | 0.2644 | 7613 | 9503 | 1.146 [0.9339, 1.403] |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 260.4+/-294.8 | 260.3 | 0.06013 | 500.4 | 2272 | 0.3093 | 8857 | 9475 | 1.053 [0.7299, 1.428] |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 266.6+/-291.2 | 266.6 | 0.08411 | 506.6 | 2272 | 0.3093 | 9098 | 9475 | 0.8294 [0.5633, 1.095] |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 219.8+/-266 | 220 | 0.04491 | 369.8 | 2195 | 0.2566 | 7564 | 9475 | 1.37 [0.8858, 1.983] |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 219.8+/-265.7 | 219.8 | 0.05165 | 369.8 | 2195 | 0.2566 | 7558 | 9475 | 1.316 [0.804, 1.98] |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 245.7+/-297 | 245.7 | 0.04335 | 485.7 | 2197 | 0.2629 | 7712 | 9503 | 1.002 [0.8189, 1.182] |
| SCIP | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 234.3+/-285.7 | 234.4 | 0 | 444.4 | 2188 | 0.2526 | 7575 | 9503 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 20 | 1/1 | 8 | 0.4 | 7.56 | 0.6735 | 1 |
| HEM | 20 | 20 | 1/1 | 9 | 0.45 | 19.35 | 0.5658 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 11 | 0.55 | 20.71 | 0.2614 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 8 | 0.4 | 8.412 | 0.3025 | 1 |
| adaptive_cutsel | 20 | 20 | 1/1 | 6 | 0.3 | 4.125 | 0.6545 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 9 | 0.45 | 5.869 | 0.398 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | -0.3303% | 20 | -0.004051 | 8 | 1.601% |
| HEM | 20 | 3.262% | 20 | 0.05267 | 8 | 23.89% |
| HEM + Beam | 20 | 3.262% | 20 | 0.05267 | 9 | 21.31% |
| HEM + Structure | 20 | 0% | 20 | 0 | 10 | 10.89% |
| adaptive_cutsel | 20 | 0.7679% | 20 | 0.007735 | 7 | -6.274% |
| 23D Features Only | 20 | 0.08666% | 20 | 0.006303 | 8 | -12.48% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 16 | 0.4375 | -20.5% | -0.004035% |
| structure_with_greedy | HEM -> HEM + Structure | 16 | 0.4375 | 12.37% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 17 | 0.6471 | 20.71% | 1.55% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.5333 | 8.412% | 0.006708% |

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
