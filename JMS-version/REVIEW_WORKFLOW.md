# JMS manuscript review workflow

Source: `JMS_Review_CN.tex` in this directory. Preserve a dated original before substantial revision, and keep a change record. Do not replace the source with older copies in `../JMS/`.

Read the manuscript and trace substantive claims to source code, immutable instance/checkpoint hashes, run configuration and validation records. Use current journal and original-paper sources for external claims. Flag unsupported industrial provenance, online deployment and statistical significance instead of writing them as facts.

For experiment comparisons, align objective boundary, recipe, sample count, solver/training seed, time budget, warm-start provenance and second-stage status. Keep old makespan including activated cleaning unloading separate from product-return makespan. Offline SPBS construction cost is distinct from the main solve budget.

For active campaigns, inspect logs/checkpoints without changing inputs. Determine campaign coverage and objective from its frozen configuration rather than older review notes. Pending results stay pending in the manuscript.

After each campaign finishes, verify exit status and expected instance coverage. Independently validate available solutions under the correct model/goal; distinguish optimal, feasible timeout, no-incumbent timeout and proven infeasible. Use matched objectives and models for mode ordering. Exact values establish ordering, and a validated feasible upper bound below the competing modes’ proven optima also establishes dominance. If certification is incomplete, report bounds and identify only the ordering that remains unresolved; never infer infeasibility from timeout. Do not replace fixed-budget algorithm benchmarks with long-budget retry results.

Compile the revised Chinese source with XeLaTeX, resolve references, check equations and rendered pages, and report actual validation. Deliver the source, PDF, review findings and deferred-evidence list. A finished process alone does not imply a complete experiment. Do not promise unattended future monitoring unless a real persistent mechanism was installed and verified.
