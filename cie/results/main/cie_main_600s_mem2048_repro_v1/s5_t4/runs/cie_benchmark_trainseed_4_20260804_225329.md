# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[5]`
- Time limit: `600.0 s` per run
- Schedule-stability profile: `full`
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 200.1+/-256.8 | 200.2 | 0.04536 | 431.1 | 4414 | 1.198 | 1.533e+04 | 253.8 | n/a |
| HEM + Beam | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 200.2+/-256.6 | 200.3 | 0.0543 | 431.3 | 4414 | 1.198 | 1.536e+04 | 253.8 | n/a |
| HEM + Structure | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 221.7+/-266.7 | 221.8 | 0.03535 | 485.8 | 4826 | 1.382 | 1.723e+04 | 261.4 | n/a |
| Proposed | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.6 | 221.6+/-266.7 | 221.8 | 0.05584 | 485.7 | 4826 | 1.382 | 1.722e+04 | 261.4 | n/a |
| 23D Features Only | full | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 203.1+/-249.8 | 203.3 | 0.05434 | 401.2 | 4001 | 1.01 | 1.496e+04 | 257.7 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 9 | 0.45 | -62.43 | 0.3638 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 8 | 0.4 | -75.34 | 0.3491 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 6 | 0.3 | 6.277 | 0.2401 | 0.9604 |
| 23D Features Only | 20 | 20 | 1/1 | 6 | 0.3 | -21.31 | 0.7325 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | -18.16% | 20 | -0.1844 | 12 | -8.737% |
| HEM + Beam | 20 | -18.16% | 20 | -0.1844 | 12 | -4.213% |
| HEM + Structure | 20 | 0% | 20 | 0 | 12 | -3.906% |
| 23D Features Only | 20 | -36.57% | 20 | -0.3722 | 12 | -17.75% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 16 | 0.375 | 10.59% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 16 | 0.5 | -69.32% | 0.01245% |
| structure_with_beam | HEM + Beam -> Proposed | 15 | 0.5333 | -75.34% | 0.02547% |
| beam_with_structure | HEM + Structure -> Proposed | 17 | 0.3529 | 6.277% | 0% |

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
