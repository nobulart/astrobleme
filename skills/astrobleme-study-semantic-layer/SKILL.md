---
name: astrobleme-study-semantic-layer
description: Use when analysing, revising, validating, or reporting the astrobleme/arcuate-geometry study in /Users/craig/ECDO/papers/astrobleme, including catalogue grains, diameter metrics, spatial nulls, GEBCO candidate-ranking scores, manuscript claims, figures, tables, source precedence, and evidentiary limits.
---

# Astrobleme Study Semantic Layer

Use this skill to answer study questions with the source-backed definitions and caveats in `references/semantic-layer.md`.

## Start Here

1. Read `references/semantic-layer.md`.
2. Read `references/source-inventory.md` before selecting a source or claiming freshness.
3. Read `references/evidence.md` when a claim depends on catalogue integrity, null-model results, or candidate-ranking interpretation.
4. Verify time-sensitive or high-stakes claims against the cited local source or an authoritative external source.

## Answering Rules

- Treat raw GeoJSON features, named structures, and ranking rows as different analytical grains.
- Treat the ranking score as follow-up priority, never as impact probability.
- Separate morphology-based detection from geological verification.
- Do not reuse global-catalogue diameter results until the documented diameter-import defect is corrected and the analysis rerun.
- Preserve seed, null-replicate count, thresholds, filters, and catalogue subset whenever reporting a statistic.
- Treat manuscript prose and generated figures as derived evidence; prefer raw data plus executable code when they disagree.
- Label stale, inferred, partial, uncalibrated, or conflicted evidence explicitly.

## References

- `references/semantic-layer.md`: grains, metrics, filters, source precedence, workflows, and gotchas.
- `references/source-inventory.md`: sources checked, coverage, permissions, and update boundaries.
- `references/evidence.md`: provenance and unresolved integrity findings.
