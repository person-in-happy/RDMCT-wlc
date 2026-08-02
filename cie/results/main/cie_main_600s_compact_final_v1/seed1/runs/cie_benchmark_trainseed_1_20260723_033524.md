# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 231.6+/-284.8 | 231.6 | 0 | 441.6 | 2184 | 0.2496 | 7209 | 9503 | 0.9681 [0.8007, 1.104] |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 197.3+/-262.9 | 197.4 | 0.06556 | 347.3 | 2183 | 0.2522 | 7689 | 9503 | 1.975 [0.7984, 3.97] |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 183.2+/-256.8 | 183.2 | 0.06693 | 333.2 | 2183 | 0.2522 | 7046 | 9503 | 1.936 [0.7681, 3.812] |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.8 | 208.7+/-264.7 | 208.7 | 0.04509 | 328.7 | 2152 | 0.2386 | 7239 | 9503 | 1.234 [0.9014, 1.667] |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.8 | 207.8+/-263.6 | 207.8 | 0.05282 | 327.8 | 2152 | 0.2386 | 7216 | 9503 | 1.227 [0.8501, 1.721] |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 239.9+/-292.5 | 240 | 0.07957 | 449.9 | 2202 | 0.2608 | 7652 | 9503 | 1.079 [0.733, 1.51] |
| SCIP | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 231.7+/-284.9 | 231.8 | 0 | 441.6 | 2212 | 0.2625 | 7502 | 9503 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 20 | 1/1 | 7 | 0.35 | 8.188 | 0.3046 | 1 |
| HEM | 20 | 20 | 1/1 | 8 | 0.4 | -77.66 | 0.4376 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 9 | 0.45 | -78.65 | 0.5843 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 10 | 0.5 | -8.968 | 0.05128 | 0.2564 |
| adaptive_cutsel | 20 | 20 | 1/1 | 7 | 0.35 | 20.15 | 0.4548 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 12 | 0.6 | -4.25 | 0.01968 | 0.1181 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 2.057% | 20 | 0.02392 | 7 | 16.17% |
| HEM | 20 | 0.9389% | 20 | 0.0136 | 10 | -176.2% |
| HEM + Beam | 20 | 0.9389% | 20 | 0.0136 | 11 | -164% |
| HEM + Structure | 20 | 0% | 20 | 0 | 11 | -3.987% |
| adaptive_cutsel | 20 | 1.056% | 20 | 0.01095 | 8 | 24.55% |
| 23D Features Only | 20 | 1.661% | 20 | 0.02214 | 8 | 4.566% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 16 | 0.5625 | 13.1% | 0.005206% |
| structure_with_greedy | HEM -> HEM + Structure | 16 | 0.5625 | -77.82% | 0.03463% |
| structure_with_beam | HEM + Beam -> Proposed | 17 | 0.5294 | -78.65% | 0.2815% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.6667 | -8.968% | 0.2497% |

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
