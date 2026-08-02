# AAAI-27 Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[2]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | Time | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 232.1+/-282.9 | 442.1 | 4414 | 1.191 | 1.799e+04 | 9317 | 1.119 [0.766, 1.579] |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 252.8+/-292.6 | 492.8 | 4826 | 1.385 | 1.982e+04 | 9317 | 1.057 [0.7114, 1.559] |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 253.8+/-292.3 | 493.9 | 4826 | 1.385 | 1.992e+04 | 9317 | 1.205 [0.7438, 1.963] |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 246.4+/-296.4 | 486.4 | 4826 | 1.386 | 1.928e+04 | 9317 | 1.285 [0.8307, 2.012] |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 245.9+/-296.8 | 485.9 | 4826 | 1.386 | 1.924e+04 | 9317 | 1.318 [0.88, 2.055] |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 246.8+/-296.2 | 486.8 | 4415 | 1.189 | 1.887e+04 | 9394 | 1.207 [0.7652, 1.892] |
| SCIP | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 251.9+/-292.8 | 491.9 | 4826 | 1.382 | 1.941e+04 | 9317 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 20 | 1/1 | 10 | 0.5 | 14.08 | 0.07782 | 0.4669 |
| HEM | 20 | 20 | 1/1 | 10 | 0.5 | 22.63 | 0.2316 | 0.9262 |
| HEM + Beam | 20 | 20 | 1/1 | 8 | 0.4 | 4.344 | 0.1244 | 0.6222 |
| HEM + Structure | 20 | 20 | 1/1 | 8 | 0.4 | 9.057 | 0.285 | 0.9262 |
| adaptive_cutsel | 20 | 20 | 1/1 | 6 | 0.3 | 7.759 | 0.6226 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 7 | 0.35 | 6.967 | 0.7784 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 0% | 20 | -0.003668 | 7 | 36.12% |
| HEM | 20 | 0% | 20 | -0.0004144 | 9 | 47.46% |
| HEM + Beam | 20 | 0% | 20 | -0.0007451 | 7 | 17.7% |
| HEM + Structure | 20 | 0% | 20 | 0 | 7 | 19.46% |
| adaptive_cutsel | 20 | -18.16% | 20 | -0.195 | 8 | 40.11% |
| 23D Features Only | 20 | -17.96% | 20 | -0.1965 | 8 | 25.83% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 17 | 0.5294 | 17% | 8.026e-05% |
| structure_with_greedy | HEM -> HEM + Structure | 17 | 0.5294 | 21.06% | 0.06767% |
| structure_with_beam | HEM + Beam -> Proposed | 15 | 0.5333 | 4.344% | 0.01043% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.5333 | 9.057% | 0.0001611% |

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
