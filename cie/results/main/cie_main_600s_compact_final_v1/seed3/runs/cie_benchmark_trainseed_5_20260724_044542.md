# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 210.2+/-272.5 | 210.4 | 0.05394 | 390.2 | 2207 | 0.262 | 7236 | 9475 | n/a |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 211+/-271.6 | 210.9 | 0.05503 | 391 | 2207 | 0.262 | 7290 | 9475 | n/a |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 209.7+/-259.2 | 209.8 | 0.04376 | 359.6 | 2195 | 0.2565 | 7329 | 9475 | n/a |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 208.8+/-259.3 | 208.7 | 0.05999 | 358.8 | 2195 | 0.2565 | 7304 | 9475 | n/a |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.8 | 201.4+/-260.1 | 201.5 | 0.04608 | 321.4 | 2058 | 0.1923 | 6420 | 9503 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 5 | 0.25 | 6.428 | 0.8104 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 6 | 0.3 | 8.044 | 0.6752 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 6 | 0.3 | 11.52 | 0.6236 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 8 | 0.4 | 7.885 | 0.8096 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 0.4709% | 20 | 0.005494 | 10 | 1.853% |
| HEM + Beam | 20 | 0.4709% | 20 | 0.005494 | 10 | -1.082% |
| HEM + Structure | 20 | 0% | 20 | 0 | 10 | 12.62% |
| 23D Features Only | 20 | -6.222% | 20 | -0.06427 | 11 | 13.99% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 16 | 0.5 | -6.342% | 2.2e-05% |
| structure_with_greedy | HEM -> HEM + Structure | 16 | 0.4375 | -25.37% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 16 | 0.375 | 8.044% | -0.002196% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.4 | 11.52% | 0% |

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
