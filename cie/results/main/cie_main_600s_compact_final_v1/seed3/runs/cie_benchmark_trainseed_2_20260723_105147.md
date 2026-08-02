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
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 224.7+/-268.3 | 224.8 | 0.05914 | 404.7 | 2180 | 0.2493 | 7917 | 9503 | n/a |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 236.4+/-279.6 | 236.5 | 0.06866 | 446.4 | 2181 | 0.2503 | 8069 | 9503 | n/a |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 227.3+/-269.8 | 227.4 | 0.04557 | 377.4 | 2195 | 0.2572 | 7691 | 9475 | n/a |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 226.7+/-269.3 | 226.7 | 0.06057 | 376.7 | 2195 | 0.2572 | 7693 | 9475 | n/a |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.8 | 214.3+/-265.8 | 214.4 | 0.04481 | 334.4 | 2085 | 0.2084 | 7339 | 9475 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 8 | 0.4 | 13.07 | 0.552 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 8 | 0.4 | 7.979 | 0.5 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 8 | 0.4 | -1.009 | 0.6904 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 9 | 0.45 | -3.472 | 0.3702 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | -0.5273% | 20 | -0.007931 | 9 | 9.986% |
| HEM + Beam | 20 | -0.4901% | 20 | -0.006899 | 7 | 2.706% |
| HEM + Structure | 20 | 0% | 20 | 0 | 11 | 8.667% |
| 23D Features Only | 20 | -4.93% | 20 | -0.04878 | 12 | 20.37% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 15 | 0.3333 | 6.804% | -0.1676% |
| structure_with_greedy | HEM -> HEM + Structure | 15 | 0.6 | 12.44% | 6.373% |
| structure_with_beam | HEM + Beam -> Proposed | 14 | 0.5714 | 7.979% | 0.6668% |
| beam_with_structure | HEM + Structure -> Proposed | 16 | 0.5 | -1.009% | 0.003367% |

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
