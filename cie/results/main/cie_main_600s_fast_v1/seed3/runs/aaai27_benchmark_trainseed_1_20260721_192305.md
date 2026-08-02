# AAAI-27 Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | Time | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 255.8+/-292.7 | 495.8 | 4826 | 1.384 | 1.914e+04 | 9317 | 1.155 [0.7969, 1.602] |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 248.4+/-288.8 | 458.4 | 4415 | 1.206 | 1.909e+04 | 9394 | 1.309 [0.9266, 1.975] |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 253.4+/-292 | 493.4 | 4826 | 1.383 | 1.939e+04 | 9317 | 1.228 [0.8908, 1.79] |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 261.9+/-291.2 | 501.9 | 4826 | 1.39 | 1.961e+04 | 9317 | 0.9115 [0.7103, 1.093] |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 260.1+/-291 | 500.1 | 4826 | 1.39 | 1.954e+04 | 9317 | 0.9778 [0.7318, 1.239] |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 258.2+/-289.3 | 498.2 | 4826 | 1.377 | 1.946e+04 | 9317 | 0.9372 [0.6244, 1.314] |
| SCIP | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.55 | 274.8+/-302 | 544.8 | 4860 | 1.414 | 2.016e+04 | 9317 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 20 | 1/1 | 8 | 0.4 | 4.017 | 0.5283 | 1 |
| HEM | 20 | 20 | 1/1 | 6 | 0.3 | -9.063 | 0.9307 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 5 | 0.25 | -9.951 | 0.9331 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 8 | 0.4 | 14.21 | 0.6118 | 1 |
| adaptive_cutsel | 20 | 20 | 1/1 | 4 | 0.2 | -27.8 | 0.9851 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 8 | 0.4 | 4.689 | 0.6604 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 1.831% | 20 | 0.02442 | 7 | 7.661% |
| HEM | 20 | -17.96% | 20 | -0.1839 | 8 | -16.15% |
| HEM + Beam | 20 | 0% | 20 | -0.00666 | 6 | -21.46% |
| HEM + Structure | 20 | 0% | 20 | 0.0004281 | 10 | 25.58% |
| adaptive_cutsel | 20 | 0% | 20 | -0.00588 | 8 | -39.2% |
| 23D Features Only | 20 | 0% | 20 | -0.01275 | 10 | 7.37% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 16 | 0.4375 | 8.457% | -8.032e-05% |
| structure_with_greedy | HEM -> HEM + Structure | 16 | 0.25 | -20.59% | -0.02771% |
| structure_with_beam | HEM + Beam -> Proposed | 14 | 0.3571 | -9.951% | -0.02698% |
| beam_with_structure | HEM + Structure -> Proposed | 18 | 0.4444 | 14.21% | 0% |

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
