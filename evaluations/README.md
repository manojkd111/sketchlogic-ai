# evaluations/ — extraction quality benchmarks

**Status: placeholder (Phase 1).** Results land in `results/` (git-ignored).

Planned metrics, comparing a predicted `GraphDocument` to a gold one:

| Metric | Definition |
| --- | --- |
| Schema validity rate | % of model outputs that validate against `graph.v1.json` without repair |
| Node F1 | Label-normalised node matching (fuzzy string + bbox IoU when available) |
| Edge F1 (directed) | Matched source→target pairs over matched nodes; direction must agree |
| Group accuracy | % of nodes assigned to the correct group |
| Inferred-edge calibration | Precision of `inferred` edges per confidence bucket (ECE) |
| Observed/inferred confusion | How often drawn arrows are mislabelled inferred and vice versa |

Every model or prompt change must report these numbers against a fixed test split before it is
promoted to the default provider.
