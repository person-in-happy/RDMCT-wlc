# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[2]`
- Time limit: `1200.0 s` per run
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.1093 | 2400 | 7156 | 0.9267 | 5.735e+04 | 9165 | n/a |
| HEM + Beam | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.104 | 2400 | 7156 | 0.9267 | 5.644e+04 | 9165 | n/a |
| HEM + Structure | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 2941 | 0.1925 | 2400 | 7147 | 0.9254 | 5.704e+04 | 9165 | n/a |
| Proposed | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.08581 | 2400 | 7147 | 0.9273 | 5.747e+04 | 9165 | n/a |
| 23D Features Only | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1200+/-0 | 1200 | 0.09327 | 2400 | 7153 | 0.9326 | 5.702e+04 | 9165 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 9 | 9 | 1/1 | 3 | 0.3333 | 0.5416 | 0.7871 | 1 |
| HEM + Beam | 9 | 9 | 1/1 | 3 | 0.3333 | -0.7822 | 0.7695 | 1 |
| HEM + Structure | 9 | 9 | 1/1 | 5 | 0.5556 | -0.2655 | 0.4727 | 1 |
| 23D Features Only | 9 | 9 | 1/1 | 3 | 0.3333 | -0.06464 | 0.7148 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 9 | 0.2552% | 9 | -0.0005771 | 0 | n/a% |
| HEM + Beam | 9 | 0.2552% | 9 | -0.0005771 | 0 | n/a% |
| HEM + Structure | 9 | 0% | 9 | -0.001849 | 0 | n/a% |
| 23D Features Only | 9 | 0.1839% | 9 | 0.005337 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.5556 | 1.254% | 0.03397% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.4444 | 0.6552% | -0.1933% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.3333 | -0.7822% | -1.174% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.5556 | -0.2655% | 0.1178% |

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
