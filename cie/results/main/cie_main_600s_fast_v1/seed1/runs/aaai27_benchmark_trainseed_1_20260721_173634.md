# AAAI-27 Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | Time | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 236.9+/-281.2 | 446.9 | 4414 | 1.202 | 1.744e+04 | 9317 | 1.002 [0.8631, 1.19] |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 240.4+/-280.1 | 420.4 | 3999 | 1.009 | 1.848e+04 | 9345 | 0.8597 [0.6744, 1.023] |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 244.2+/-283.4 | 424.2 | 3999 | 1.008 | 1.878e+04 | 9345 | 0.8252 [0.636, 0.9911] |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 249.8+/-294.6 | 489.8 | 4453 | 1.209 | 1.849e+04 | 9345 | 1.02 [0.9688, 1.083] |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 249.9+/-294.5 | 489.9 | 4453 | 1.209 | 1.849e+04 | 9345 | 0.8498 [0.6667, 1.015] |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 234.3+/-285.8 | 444.3 | 4414 | 1.193 | 1.813e+04 | 9317 | 1.426 [0.8125, 2.466] |
| SCIP | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 249.2+/-294.7 | 489.1 | 4456 | 1.217 | 1.912e+04 | 9345 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 20 | 1/1 | 8 | 0.4 | 6.985 | 0.2931 | 1 |
| HEM | 20 | 20 | 1/1 | 9 | 0.45 | 9.393 | 0.2267 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 7 | 0.35 | 11.89 | 0.398 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 7 | 0.35 | 6.543 | 0.6208 | 1 |
| adaptive_cutsel | 20 | 20 | 1/1 | 8 | 0.4 | -11.58 | 0.2165 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 6 | 0.3 | -50.24 | 0.6334 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 0.09337% | 20 | 0.008231 | 8 | 13.97% |
| HEM | 20 | -20.41% | 20 | -0.1998 | 9 | 10.13% |
| HEM + Beam | 20 | -20.41% | 20 | -0.2001 | 8 | 14% |
| HEM + Structure | 20 | 0% | 20 | 0 | 7 | 14.29% |
| adaptive_cutsel | 20 | -14.61% | 20 | -0.006494 | 7 | 30.47% |
| 23D Features Only | 20 | -14.61% | 20 | -0.01514 | 8 | -102.2% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 17 | 0.5294 | 3.746% | 0.0001231% |
| structure_with_greedy | HEM -> HEM + Structure | 17 | 0.5294 | 21.89% | 1.006% |
| structure_with_beam | HEM + Beam -> Proposed | 16 | 0.4375 | 11.89% | 0% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.4667 | 6.543% | 0% |

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
