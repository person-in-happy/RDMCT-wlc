# JMS scope-oriented revision notes

## Revision basis

- The current JMS scope emphasizes manufacturing research at the systems level, from equipment to the extended enterprise, and lists pure shop-floor scheduling, modeling/simulation, and resource optimization as topics that are generally outside its scope.
- The local `文献/jms.pdf` article was retained as the formatting and reference-style sample.
- Three recent JMS papers were added to the Introduction to establish the systems-research context: production--logistics coordination through a partially decentralized architecture; coupled layout and scheduling in matrix manufacturing; and scalable control of multi-stage manufacturing lines.

## Main changes in this version

1. Reframed the title and Abstract around manufacturing-system coordination of a dual-source equipment cell. The MILP and learning-enhanced exact solver are presented as the operational model and decision engine, rather than as isolated algorithmic contributions.
2. Added a system-oriented literature bridge and reformulated the research gap as the missing chain from equipment-configuration inputs to a verifiable execution timeline.
3. Reorganized the contribution statements around: (i) the equipment-cell state--event model; (ii) throughput-first and operating-quality-second decision logic; and (iii) finite-time delivery and certification of feasible plans.
4. Renamed Sections 2--4 and rewrote their openings so that they follow the sequence of manufacturing-system architecture, operational modeling, exact decision support, and system experiments.
5. Expanded the system-integration discussion to state the information interface among upper-level batch release, the equipment-cell decision layer, and lower-level equipment actions.
6. Rewrote the Conclusions to report the system decision chain first, followed by the experimentally supported results.
7. Synchronized the English manuscript to the Chinese review manuscript and added the same three verified JMS references to both files.

## PECVD background revision

- Rewrote the Abstract, opening of the Introduction, research gap, and Conclusions around the causal chain from established CT use to advanced-process PECVD requirements, multi-space rotating chambers, chamber-position protection for carbon-containing films, reusable dummy-wafer filling, dual-source mixed flow, and wafer-residency/cadence control.
- Limited the chamber-damage statement to the equipment and process considered in the study: persistent residue creates contamination or chamber-condition risk at exposed positions. The manuscript does not generalize direct physical damage to every carbon-containing PECVD process.
- Reduced the English Abstract to 245 words and removed repeated layer-by-layer template phrasing.

## Confirmed evidence and remaining editorial risk

- Confirmed by the current experiments: the model returns checked finite-batch timelines under the modeled dual-source routes, full occupancy, cleaning, and shared-resource constraints; the reported mode, two-stage, SPBS, baseline, scale, sensitivity, and distribution-shift results are unchanged.
- Supported as a system-interface interpretation: the event timeline can connect batch and equipment-configuration inputs to robot, chamber, cleaning, and return actions, while exposing feasibility and optimality status.
- Not established by the current evidence: fab-wide throughput improvement, online closed-loop performance, or deployment on production equipment. These claims were not added.
- Residual desk-review risk remains because the empirical validation is computational and equipment-cell-level. The cover letter should therefore foreground the coupled physical topology, dual-source material flow, full-occupancy/cleaning control, and executable equipment interface; it should not describe the paper primarily as a new scheduling or cut-selection algorithm.

## Deliverables

- `JMS_Review_CN.tex` and `JMS_Review_CN.pdf`: Chinese review manuscript.
- `JMS_Submission_EN.tex` and `JMS_Submission_EN.pdf`: English submission manuscript.
- `output/pdf/`: final PDF copies for delivery.
