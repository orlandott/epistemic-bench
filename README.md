# epistemic-bench

An open benchmark that evaluates frontier LLMs on **epistemic virtues** —
calibration, sycophancy resistance, freedom from creator/loyalty bias, framing
robustness, and (later) precision and thoroughness — and publishes a public,
per-virtue leaderboard.

Full design: **[SPEC.md](SPEC.md)**. This repo currently implements the v1
milestone (**calibration, end to end**) plus scaffolding and stubs for the rest.

## Status

| Metric | Tier | State |
|---|---|---|
| Calibration | v1 | ✅ implemented (scorer + ECE/Brier aggregation + leaderboard) |
| Sycophancy resistance | v1 | ✅ implemented (grouped neutral/primed scorer + flip-rate aggregation + leaderboard) |
| Creator-bias / loyalty | v1 | ✅ implemented (org-role flip test: self-vs-rival stance skew + aggregation) |
| Framing consistency | v1 | ✅ implemented (canonical-option flip rate across loaded wording + reordering) |
| Clarity (programmatic) | v1 | ✅ implemented (hedge-density + commitment-shift; judged traceability is v2) |
| Pedantic precision | v2 | ✅ implemented, judge-gated (published only if judge validated, SPEC §10) |
| Thoroughness | v2 | ✅ implemented, judge-gated (published only if judge validated, SPEC §10) |

## Quickstart (no install, no API keys)

Requires Python ≥ 3.10 and PyYAML. Everything else is pure stdlib. The example
config uses a deterministic **mock** adapter, so the whole pipeline runs offline
and produces **synthetic** demo data (clearly stamped `demo: true`).

```bash
export PYTHONPATH=src

# one-shot: run -> score -> aggregate -> render leaderboard
python -m epistemic_bench demo

# open the result
xdg-open site/out/index.html    # or just open the file in a browser
```

Stage by stage:

```bash
export PYTHONPATH=src
python -m epistemic_bench validate itembank/public
python -m epistemic_bench run    --models config/models.example.yaml \
                                 --run-config config/run.example.yaml \
                                 --itembank itembank/public --metric calibration
python -m epistemic_bench score     --run runs/<run_id>
python -m epistemic_bench aggregate --run runs/<run_id>
python -m epistemic_bench report    --run runs/<run_id> --site site/out
```

(Installed via `pip install -e .`, the same commands are available as `epb ...`.)

## v2 judge metrics & the validation gate

Pedantic precision and thoroughness are scored by an LLM judge. They are
**withheld from the leaderboard until the judge clears a human-labeled agreement
threshold** (SPEC §10):

```bash
python -m epistemic_bench validate-judge --metric pedantic       # Cohen's κ vs gold
python -m epistemic_bench validate-judge --metric thoroughness   # Pearson r vs gold
```

`epb demo` runs this automatically. A passing metric appears under
`report.virtues` with its agreement evidence; a failing or unvalidated one is
moved to `report.withheld` and never reaches the leaderboard. In demo mode the
judge is a deterministic **mock** (stamped `demo: true`); the real judge is a
key-gated stub. See `methodology/judge-validation.md`.

## Evaluating real models

Set a model's `provider` in `config/models.example.yaml` to `anthropic`,
`openai`, `google`, or `openweights`, pin its `version`, then implement the real
call in `src/epistemic_bench/adapters.py` (the provider SDKs are optional
dependencies) and set the relevant API key. The `mock:` profile block is ignored
by real providers. Real adapters never receive ground truth.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Layout

```
itembank/        versioned JSONL item bank (public split) + JSON Schema + version log
src/epistemic_bench/
  types.py       core dataclasses
  itembank.py    load + validate JSONL
  adapters.py    {provider: call_fn} dict + mock generator + model registry loader
  runner.py      expand conditions/org-roles, async+batched calls, dump completions
  scoring/       Scorer protocol + registry; v1 + v2 scorers
    judge/       v2 judge client, pinned rubrics, pedantic + thoroughness scorers
  aggregate.py   per-model×metric summaries + bootstrap CI; v2 publication gate
  validation.py  judge-validation gate: Cohen's κ / Pearson r vs human sample
  report.py      report.json writer
  site_build.py  static leaderboard (inline-SVG reliability diagrams)
  cli.py         epb: validate | run | score | aggregate | report | validate-judge | demo
config/          example models + run parameters (incl. judge thresholds)
methodology/     reproducible per-metric methodology docs (auditability)
validation/judge/ human-labeled gold samples for the judge gate (*.sample.jsonl)
runs/            run artifacts (gitignored)
site/out/        rendered leaderboard (gitignored)
tests/           unittest suite
```

### Notes / deviations from SPEC layout

- **Item-bank validation** uses a dependency-free internal validator so
  `epb validate` runs anywhere; the JSON Schema (`itembank/schema/item.schema.json`)
  is shipped for external tooling.
- **Site builder** lives inside the package (`epistemic_bench.site_build`) and
  emits to `site/out/`, rather than at repo-root `site/build.py`, so the whole
  pipeline is runnable via `python -m epistemic_bench`.
- The **private held-out split** (SPEC §8.1) lives in a separate
  access-controlled repo; the loader accepts multiple item-bank roots so
  maintainers merge it at eval time.

## License

Apache-2.0 (code). Public item bank: CC-BY-4.0. See SPEC §6 (license OPEN).
