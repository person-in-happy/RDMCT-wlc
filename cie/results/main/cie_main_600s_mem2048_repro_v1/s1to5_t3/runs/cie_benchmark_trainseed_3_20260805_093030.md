# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1, 2, 3, 4, 5]`
- Time limit: `600.0 s` per run
- Schedule-stability profile: `full`
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.64 | 215.1+/-254.4 | 215.3 | 0.02821 | 452.8 | 4496 | 1.236 | 1.652e+04 | 268.3 | n/a |
| HEM + Beam | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.64 | 215.4+/-254.2 | 215.6 | 0.04544 | 453.1 | 4496 | 1.236 | 1.653e+04 | 268.3 | n/a |
| HEM + Structure | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.64 | 218+/-253.2 | 218.2 | 0.04489 | 455.7 | 4427 | 1.24 | 1.645e+04 | 263.6 | n/a |
| Proposed | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.63 | 218.8+/-254.1 | 218.9 | 0.02741 | 463.1 | 4510 | 1.278 | 1.653e+04 | 259 | n/a |
| 23D Features Only | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.61 | 221.9+/-258.7 | 222.1 | 0.02621 | 479.4 | 4662 | 1.311 | 1.687e+04 | 264.2 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 100 | 100 | 1/1 | 44 | 0.44 | -13.46 | 0.1104 | 0.2473 |
| HEM + Beam | 100 | 100 | 1/1 | 39 | 0.39 | -22.2 | 0.3661 | 0.3661 |
| HEM + Structure | 100 | 100 | 1/1 | 45 | 0.45 | 13.11 | 0.08242 | 0.2473 |
| 23D Features Only | 100 | 100 | 1/1 | 45 | 0.45 | -72.2 | 0.03099 | 0.124 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 100 | -15.67% | 100 | -0.04107 | 60 | -14.65% |
| HEM + Beam | 100 | -15.67% | 100 | -0.04116 | 60 | -11.39% |
| HEM + Structure | 100 | -3.724% | 100 | -0.0375 | 63 | -1.853% |
| 23D Features Only | 100 | -8.293% | 100 | 0.03299 | 59 | -12.66% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 80 | 0.4 | 8.956% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 80 | 0.4875 | -21.04% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 75 | 0.52 | -22.2% | 0.01572% |
| beam_with_structure | HEM + Structure -> Proposed | 82 | 0.5488 | 13.11% | 0.0001352% |

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
