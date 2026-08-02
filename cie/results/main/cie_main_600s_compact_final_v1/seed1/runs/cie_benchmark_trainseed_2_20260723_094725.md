# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 230.4+/-280.8 | 230.6 | 0.06564 | 440.4 | 2236 | 0.2724 | 7739 | 9503 | n/a |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 224.8+/-273.9 | 224.7 | 0.0751 | 404.8 | 2227 | 0.269 | 7741 | 9503 | n/a |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 227.6+/-285.1 | 227.7 | 0.04795 | 407.6 | 2190 | 0.2561 | 7655 | 9503 | n/a |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 227.9+/-285.5 | 228 | 0.04639 | 407.9 | 2225 | 0.2657 | 7653 | 9503 | n/a |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.7 | 204.8+/-272.6 | 204.8 | 0.05258 | 384.8 | 2223 | 0.2729 | 7401 | 9503 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 8 | 0.4 | 10.22 | 0.4181 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 7 | 0.35 | 8.112 | 0.398 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 5 | 0.25 | 5.386 | 0.8943 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 10 | 0.5 | 0.9781 | 0.3082 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 0.3059% | 20 | 0.006716 | 7 | 53.5% |
| HEM + Beam | 20 | -0.01204% | 20 | 0.003321 | 7 | 38.84% |
| HEM + Structure | 20 | -1.414% | 20 | -0.009617 | 10 | 9.702% |
| 23D Features Only | 20 | -0.1316% | 20 | 0.007173 | 10 | -3.471% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 15 | 0.6 | -0.3772% | 0.02201% |
| structure_with_greedy | HEM -> HEM + Structure | 15 | 0.4667 | 10.74% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 14 | 0.5 | 8.112% | 0.4509% |
| beam_with_structure | HEM + Structure -> Proposed | 16 | 0.3125 | 5.386% | -0.1487% |

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
