# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1, 2, 3, 4]`
- Time limit: `600.0 s` per run
- Schedule-stability profile: `full`
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 80 | 1 | 0.6375 | 221.4+/-252.3 | 221.5 | 0.04649 | 460.7 | 4417 | 1.197 | 1.695e+04 | 260 | n/a |
| HEM + Beam | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 80 | 1 | 0.6375 | 221.4+/-252.3 | 221.5 | 0.06193 | 460.7 | 4417 | 1.197 | 1.684e+04 | 260 | n/a |
| HEM + Structure | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 80 | 1 | 0.6125 | 218.7+/-258 | 218.9 | 0.06139 | 474.6 | 4723 | 1.339 | 1.695e+04 | 264.1 | n/a |
| Proposed | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 80 | 1 | 0.6125 | 219+/-257.8 | 219.2 | 0.08583 | 474.9 | 4723 | 1.339 | 1.694e+04 | 264.2 | n/a |
| 23D Features Only | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 80 | 1 | 0.6375 | 213.4+/-255.5 | 213.5 | 0.05389 | 452.7 | 4340 | 1.166 | 1.603e+04 | 265 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 80 | 80 | 1/1 | 33 | 0.4125 | 9.298 | 0.5408 | 1 |
| HEM + Beam | 80 | 80 | 1/1 | 31 | 0.3875 | 6.184 | 0.5076 | 1 |
| HEM + Structure | 80 | 80 | 1/1 | 28 | 0.35 | 4.051 | 0.4097 | 1 |
| 23D Features Only | 80 | 80 | 1/1 | 29 | 0.3625 | -18.1 | 0.8592 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 80 | -16.69% | 80 | -0.1419 | 48 | -8.11% |
| HEM + Beam | 80 | -16.69% | 80 | -0.1416 | 48 | -2.213% |
| HEM + Structure | 80 | -5.453e-15% | 80 | -0.0001897 | 49 | -7.509% |
| 23D Features Only | 80 | -18.85% | 80 | -0.1726 | 48 | -37.16% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 66 | 0.4242 | 6.058% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 66 | 0.4697 | -10.8% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 68 | 0.4559 | 6.184% | 0% |
| beam_with_structure | HEM + Structure -> Proposed | 66 | 0.4242 | 4.051% | 0% |

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
