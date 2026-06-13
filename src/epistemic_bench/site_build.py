"""Static leaderboard builder (SPEC §7.7).

Renders ``report.json`` to a single self-contained ``index.html`` with inline-SVG
reliability diagrams. No JS framework, no plotting deps. This is the only place
visualization lives.

Note (implementation deviation from SPEC layout): the generator lives inside the
package (importable) and emits to ``site/out/`` rather than living at repo-root
``site/build.py``; keeps everything runnable via ``python -m epistemic_bench``.
"""

from __future__ import annotations

import html
from pathlib import Path

from .jsonlio import read_json


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _fmt(x, nd: int = 3) -> str:
    return "—" if x is None else f"{float(x):.{nd}f}"


def _reliability_svg(bins: list[dict], w: int = 260, h: int = 260, pad: int = 34) -> str:
    iw, ih = w - 2 * pad, h - 2 * pad

    def px(x: float) -> float:
        return pad + x * iw

    def py(y: float) -> float:
        return h - pad - y * ih

    parts = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="reliability diagram">']
    parts.append(f'<rect x="{pad}" y="{pad}" width="{iw}" height="{ih}" fill="#fff" stroke="#cbd5e1"/>')
    # perfect-calibration diagonal
    parts.append(f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(1)}" y2="{py(1)}" stroke="#94a3b8" stroke-dasharray="4 3"/>')
    # 0.5 gridlines
    parts.append(f'<line x1="{px(0.5)}" y1="{py(0)}" x2="{px(0.5)}" y2="{py(1)}" stroke="#eef2f7"/>')
    parts.append(f'<line x1="{px(0)}" y1="{py(0.5)}" x2="{px(1)}" y2="{py(0.5)}" stroke="#eef2f7"/>')

    pts = [b for b in bins if b.get("n", 0) > 0]
    if pts:
        poly = " ".join(f"{px(b['mean_conf']):.1f},{py(b['accuracy']):.1f}" for b in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="#2563eb" stroke-width="1.5" opacity="0.7"/>')
        for b in pts:
            r = max(2.5, min(10.0, 1.6 * (b["n"] ** 0.5)))
            parts.append(
                f'<circle cx="{px(b["mean_conf"]):.1f}" cy="{py(b["accuracy"]):.1f}" r="{r:.1f}" '
                f'fill="#2563eb" fill-opacity="0.55" stroke="#1e3a8a"/>'
            )

    # axis labels + ticks
    parts.append(f'<text x="{px(0.5):.0f}" y="{h - 6}" text-anchor="middle" font-size="11" fill="#475569">stated confidence</text>')
    parts.append(f'<text x="12" y="{py(0.5):.0f}" text-anchor="middle" font-size="11" fill="#475569" transform="rotate(-90 12 {py(0.5):.0f})">accuracy</text>')
    for t in (0.0, 0.5, 1.0):
        parts.append(f'<text x="{px(t):.0f}" y="{h - pad + 12}" text-anchor="middle" font-size="9" fill="#94a3b8">{t:g}</text>')
        parts.append(f'<text x="{pad - 6}" y="{py(t):.0f}" text-anchor="end" font-size="9" fill="#94a3b8">{t:g}</text>')
    parts.append("</svg>")
    return "".join(parts)


_STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       margin: 0; color: #0f172a; background: #f8fafc; }
.wrap { max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }
h1 { margin: 0 0 4px; font-size: 26px; }
h2 { margin: 32px 0 10px; font-size: 19px; }
.sub { color: #475569; margin: 0 0 18px; }
.banner { background: #fef3c7; border: 1px solid #f59e0b; color: #7c2d12;
          padding: 10px 14px; border-radius: 8px; margin: 0 0 18px; font-size: 14px; }
.note { color: #475569; font-size: 13px; margin: 6px 0 14px; }
table { border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #e2e8f0;
        border-radius: 8px; overflow: hidden; font-size: 14px; }
th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid #eef2f7; }
th { background: #f1f5f9; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-top: 16px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; }
.card h3 { margin: 0 0 2px; font-size: 15px; }
.card .maker { color: #64748b; font-size: 12px; margin: 0 0 8px; }
.legend { color: #64748b; font-size: 12px; margin-top: 10px; }
footer { margin-top: 36px; color: #64748b; font-size: 12px; border-top: 1px solid #e2e8f0; padding-top: 14px; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
"""


def _calibration_section(report: dict) -> str:
    virtue = report.get("virtues", {}).get("calibration")
    if not virtue:
        return "<p>No calibration results in this report.</p>"
    by_model = virtue["by_model"]
    models = report.get("models", [])

    rows = []
    cards = []
    for m in models:
        mid = m["id"]
        d = by_model.get(mid)
        if not d:
            continue
        raw = d.get("raw", {})
        ci = d.get("ci")
        ci_txt = f' <span style="color:#94a3b8">({_fmt(ci[0],2)}–{_fmt(ci[1],2)})</span>' if ci else ""
        rows.append(
            "<tr>"
            f"<td>{_esc(m['display_name'])}</td>"
            f"<td>{_esc(m.get('maker',''))}</td>"
            f'<td class="num">{_fmt(raw.get("accuracy"),3)}</td>'
            f'<td class="num">{_fmt(raw.get("ece"),3)}</td>'
            f'<td class="num">{_fmt(raw.get("brier"),3)}</td>'
            f'<td class="num"><b>{_fmt(d.get("score"),3)}</b>{ci_txt}</td>'
            f'<td class="num">{int(raw.get("n_items",0))}</td>'
            "</tr>"
        )
        cards.append(
            '<div class="card">'
            f"<h3>{_esc(m['display_name'])}</h3>"
            f'<p class="maker">{_esc(m.get("maker",""))} · score 1−ECE = {_fmt(d.get("score"),3)}</p>'
            f"{_reliability_svg(d.get('reliability', []))}"
            "</div>"
        )

    return (
        f'<p class="note">{_esc(virtue.get("definition",""))}. Points on the dashed diagonal are '
        "perfectly calibrated; above = underconfident, below = overconfident. Point size ∝ items in bin.</p>"
        "<table><thead><tr>"
        "<th>Model</th><th>Maker</th><th class='num'>Accuracy</th><th class='num'>ECE</th>"
        "<th class='num'>Brier</th><th class='num'>Score (1−ECE)</th><th class='num'>n</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        '<div class="cards">' + "".join(cards) + "</div>"
    )


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def _generic_virtue_section(virtue: dict, models: list) -> str:
    """Render any scored virtue as a table: Model | Maker | Score | raw cols | n."""
    by_model = virtue["by_model"]
    cols: set[str] = set()
    for m in models:
        d = by_model.get(m["id"])
        if d:
            cols |= set(d.get("raw", {}).keys())
    cols.discard("n_items")
    col_order = sorted(cols)

    head = (
        "<tr><th>Model</th><th>Maker</th><th class='num'>Score</th>"
        + "".join(f"<th class='num'>{_esc(c.replace('_', ' '))}</th>" for c in col_order)
        + "<th class='num'>n</th></tr>"
    )
    rows = []
    for m in models:
        d = by_model.get(m["id"])
        if not d:
            continue
        raw = d.get("raw", {})
        ci = d.get("ci")
        ci_txt = f' <span style="color:#94a3b8">({_fmt(ci[0],2)}–{_fmt(ci[1],2)})</span>' if ci else ""
        rows.append(
            "<tr>"
            f"<td>{_esc(m['display_name'])}</td><td>{_esc(m.get('maker',''))}</td>"
            f"<td class='num'><b>{_fmt(d.get('score'),3)}</b>{ci_txt}</td>"
            + "".join(f"<td class='num'>{_fmt(raw.get(c),3)}</td>" for c in col_order)
            + f"<td class='num'>{int(raw.get('n_items',0))}</td></tr>"
        )
    definition = virtue.get("definition", "")
    return (
        f'<p class="note">{_esc(definition)}.</p>'
        "<table><thead>" + head + "</thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def build_site(report_path: Path | str, out_dir: Path | str) -> Path:
    report = read_json(report_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    run = report.get("run", {})
    demo = report.get("demo", False)
    banner = (
        '<div class="banner"><b>DEMO — synthetic data.</b> These numbers were produced by the '
        "deterministic <code>mock</code> adapter for pipeline demonstration. They are NOT real model "
        "results.</div>"
        if demo
        else ""
    )

    models_meta = ", ".join(
        f"{_esc(m['display_name'])} (<code>{_esc(m.get('provider',''))}</code> · {_esc(m.get('version','') or 'n/a')})"
        for m in report.get("models", [])
    )

    models = report.get("models", [])
    virtues = report.get("virtues", {})
    # Other scored virtues (anything beyond calibration with a non-null score).
    other_sections = []
    implemented = {"calibration"}
    for name, virtue in virtues.items():
        if name == "calibration":
            continue
        if any(d.get("score") is not None for d in virtue.get("by_model", {}).values()):
            implemented.add(name)
            other_sections.append(f"<h2>{_esc(_title(name))}</h2>{_generic_virtue_section(virtue, models)}")
    other_html = "".join(other_sections)
    remaining = [v for v in ("creator_bias", "framing", "clarity") if v not in implemented]
    remaining_txt = ", ".join(_title(v) for v in remaining) or "—"

    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>epistemic-bench — leaderboard</title>
<style>{_STYLE}</style></head>
<body><div class="wrap">
<h1>epistemic-bench</h1>
<p class="sub">A per-virtue profile of epistemic behavior in frontier LLMs. No single composite score, by design.</p>
{banner}
<h2>Calibration</h2>
{_calibration_section(report)}
{other_html}
<p class="legend">Remaining virtues ({_esc(remaining_txt)}) are specified in <code>SPEC.md</code> and
scaffolded as stubs; they will appear here once implemented.</p>
<footer>
<div>{report.get('note','')}</div>
<div style="margin-top:6px">Run <code>{_esc(run.get('run_id','?'))}</code> ·
item bank <code>{_esc(run.get('bank_version','?'))}</code> ·
seed <code>{_esc(run.get('seed','?'))}</code> ·
code <code>{_esc(run.get('code_sha','?'))}</code> ·
generated {_esc(report.get('generated_at','?'))}</div>
<div style="margin-top:6px">Models: {models_meta}</div>
<div style="margin-top:6px">Methodology: <code>methodology/calibration.md</code> · Design: <code>SPEC.md</code></div>
</footer>
</div></body></html>"""

    path = out / "index.html"
    path.write_text(body, encoding="utf-8")
    return path
