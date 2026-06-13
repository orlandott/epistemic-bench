"""v2 judge-dependent scorers (SPEC §3, §10).

These scorers ARE registered (so the pipeline can compute them) but a judged
metric is published to the leaderboard ONLY after clearing the validation gate —
a human-labeled sample with agreement at or above threshold, recorded under
``validation/judge/`` (see ``methodology/judge-validation.md``). The gate is
enforced at report time in ``aggregate.to_report``. v2 scorers also require a
judge injected via ``ScoringContext.judge``.
"""
