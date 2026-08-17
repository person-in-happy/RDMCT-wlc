# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `1200.0 s` per run
- Schedule-stability profile: `full`
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1141+/-0.7718 | 1142 | 0.0967 | 2400 | 9254 | 1.534 | 7.282e+04 | 737.7 | n/a |
| HEM + Beam | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.8952 | 1141 | 0.08827 | 2400 | 9254 | 1.531 | 7.249e+04 | 737.7 | n/a |
| HEM + Structure | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1141+/-0.8827 | 1142 | 0.06697 | 2400 | 9227 | 1.518 | 7.21e+04 | 716.6 | n/a |
| Proposed | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1141+/-0.7819 | 1142 | 0.05097 | 2400 | 9227 | 1.518 | 7.211e+04 | 716.6 | n/a |
| 23D Features Only | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1141+/-0.879 | 1142 | 0.04591 | 2400 | 9990 | 1.82 | 7.778e+04 | 780.2 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 9 | 9 | 1/1 | 6 | 0.6667 | 1.789 | 0.1797 | 0.7188 |
| HEM + Beam | 9 | 9 | 1/1 | 6 | 0.6667 | 1.148 | 0.1797 | 0.7188 |
| HEM + Structure | 9 | 9 | 1/1 | 5 | 0.5556 | -0.02001 | 0.3672 | 0.7188 |
| 23D Features Only | 9 | 9 | 1/1 | 6 | 0.6667 | 6.585 | 0.2305 | 0.7188 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 9 | 0.6891% | 9 | 0.01638 | 0 | n/a% |
| HEM + Beam | 9 | 0.6891% | 9 | 0.01348 | 0 | n/a% |
| HEM + Structure | 9 | 0% | 9 | 0 | 0 | n/a% |
| 23D Features Only | 9 | 7.259% | 9 | 0.3022 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.6667 | 0.6868% | 0.2341% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.7778 | 1.805% | 0.5461% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.6667 | 1.148% | 0.3044% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.5556 | -0.02001% | 0.002356% |

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
