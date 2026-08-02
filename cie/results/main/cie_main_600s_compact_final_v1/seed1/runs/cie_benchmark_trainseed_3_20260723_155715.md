# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 221.6+/-277.6 | 221.6 | 0.0522 | 371.6 | 2182 | 0.2527 | 7596 | 9503 | n/a |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.8 | 223.2+/-279.5 | 223.3 | 0.05763 | 343.2 | 2152 | 0.239 | 7573 | 9503 | n/a |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 227.5+/-285 | 227.6 | 0.03682 | 407.5 | 2190 | 0.2566 | 7662 | 9503 | n/a |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 227.1+/-284.3 | 227.1 | 0.04123 | 407.1 | 2190 | 0.2566 | 7662 | 9503 | n/a |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 209.6+/-271.5 | 209.6 | 0.06718 | 389.6 | 2202 | 0.2576 | 7223 | 9503 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 9 | 0.45 | 6.681 | 0.5845 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 6 | 0.3 | 1.489 | 0.7649 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 9 | 0.45 | 7.208 | 0.4906 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 9 | 0.45 | -34.6 | 0.5947 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | -0.3362% | 20 | -0.00388 | 10 | 15.69% |
| HEM + Beam | 20 | -1.65% | 20 | -0.01764 | 10 | 2.856% |
| HEM + Structure | 20 | 0% | 20 | 0 | 9 | 12.28% |
| 23D Features Only | 20 | 0.2478% | 20 | 0.001031 | 7 | 18.77% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 16 | 0.5625 | -2.412% | 0.02698% |
| structure_with_greedy | HEM -> HEM + Structure | 16 | 0.5 | 6.259% | 0.0009068% |
| structure_with_beam | HEM + Beam -> Proposed | 16 | 0.375 | 1.489% | 0% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.6 | 7.208% | 0.005373% |

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
