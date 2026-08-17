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
| HEM | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.62 | 220.5+/-258.6 | 220.7 | 0.02461 | 471.4 | 4579 | 1.274 | 1.675e+04 | 267.7 | n/a |
| HEM + Beam | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.62 | 220.6+/-258.6 | 220.8 | 0.02341 | 471.5 | 4579 | 1.273 | 1.677e+04 | 267.7 | n/a |
| HEM + Structure | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.65 | 216.4+/-252.4 | 216.5 | 0.03651 | 447.5 | 4344 | 1.203 | 1.627e+04 | 268.3 | n/a |
| Proposed | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.65 | 216.2+/-252.3 | 216.4 | 0.05477 | 447.3 | 4344 | 1.203 | 1.628e+04 | 268.3 | n/a |
| 23D Features Only | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 100 | 1 | 0.62 | 220.6+/-258.6 | 220.8 | 0.03865 | 471.5 | 4579 | 1.274 | 1.676e+04 | 267.7 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 100 | 100 | 1/1 | 44 | 0.44 | -64.98 | 0.08667 | 0.26 |
| HEM + Beam | 100 | 100 | 1/1 | 41 | 0.41 | -24.88 | 0.1231 | 0.26 |
| HEM + Structure | 100 | 100 | 1/1 | 33 | 0.33 | -1.416 | 0.8847 | 0.8847 |
| 23D Features Only | 100 | 100 | 1/1 | 45 | 0.45 | -78.79 | 0.05891 | 0.2356 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 100 | -10.35% | 100 | 0.07089 | 59 | -12.94% |
| HEM + Beam | 100 | -10.35% | 100 | 0.07082 | 59 | -12.94% |
| HEM + Structure | 100 | 0% | 100 | -8.249e-05 | 65 | -1.014% |
| 23D Features Only | 100 | -10.35% | 100 | 0.07106 | 59 | -12.67% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 81 | 0.4198 | 8.53% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 81 | 0.5185 | -32.35% | 0.006149% |
| structure_with_beam | HEM + Beam -> Proposed | 78 | 0.5256 | -24.88% | 0.01299% |
| beam_with_structure | HEM + Structure -> Proposed | 80 | 0.4125 | -1.416% | 0% |

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
