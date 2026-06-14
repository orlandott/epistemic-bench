"""Structural / golden-HTML coverage for the static leaderboard builder.

``site_build.build_site`` is the only place visualization lives, and it has been
through several rounds of chart changes with no tests. A full byte-for-byte
golden snapshot would be too brittle (the SVG geometry changes often and on
purpose), so these tests assert the *structural* invariants that should hold no
matter how the charts are styled:

* the emitted HTML is tag-balanced (open/close nesting is well formed);
* every live (scored) virtue renders exactly one leaderboard and exactly one
  (collapsed) charts panel, and calibration renders exactly one reliability
  diagram per scored model;
* demo runs are stamped with the "not real results" banner (and only those);
* the technical-detail panels are collapsed by default;
* untrusted strings (model names) are HTML-escaped, not injected;
* withheld vs. "in development" virtues land in the right place.
"""

import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

import _bootstrap  # noqa: F401  (adds src/ to path)

from epistemic_bench.site_build import VIRTUES, _is_live, build_site

# aria-label unique to the calibration reliability diagram (one per scored model).
_RELIABILITY = 'aria-label="stated confidence versus actual accuracy"'

# HTML void elements never get a closing tag; the rest must nest properly.
_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _BalanceChecker(HTMLParser):
    """Minimal well-formedness checker: tracks an open-tag stack and records any
    end tag that does not close the element on top of it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        # Self-closing (e.g. SVG <rect .../>) — already balanced.
        pass

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if not self.stack:
            self.errors.append(f"unexpected closing </{tag}> with empty stack")
        elif self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.errors.append(
                f"improper nesting: </{tag}> while inside <{self.stack[-1]}>"
            )
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.errors.append(f"stray closing </{tag}>")


def _reliability(bins):
    return [
        {"lo": lo, "hi": hi, "n": n, "mean_conf": mc, "accuracy": acc}
        for (lo, hi, n, mc, acc) in bins
    ]


def make_report(demo: bool = True, canonical_split: str = "public",
                splits_loaded=("public",)) -> dict:
    """A faithful, hand-built ``report.json`` exercising every render path:
    a charted virtue (calibration), a plain-column virtue (sycophancy), a
    bare-table virtue (creator_bias), a judge-validated virtue (thoroughness),
    a withheld virtue (pedantic) and two not-yet-built virtues (framing,
    clarity). One model name carries markup to test escaping."""
    models = [
        {"id": "m1", "display_name": "Aurora 2", "maker": "NorthLab",
         "provider": "northlab", "version": "2.0"},
        {"id": "m2", "display_name": "Beacon X", "maker": "Lumen",
         "provider": "lumen", "version": "x"},
        {"id": "m3", "display_name": "<script>alert(1)</script>", "maker": "Evil & Co",
         "provider": "evil", "version": "1.0"},
    ]
    rel = _reliability([
        (0.0, 0.5, 0, 0.0, 0.0),       # empty bin (skipped in the chart)
        (0.5, 0.7, 12, 0.62, 0.55),
        (0.7, 0.9, 30, 0.81, 0.78),
        (0.9, 1.0, 48, 0.95, 0.88),
    ])

    def cal_entry(score, acc):
        return {
            "score": score, "ci": [score - 0.03, score + 0.03],
            "raw": {"accuracy": acc, "ece": 1 - score, "brier": 0.14, "n_items": 120},
            "reliability": rel, "split": "public",
        }

    virtues = {
        "calibration": {
            "direction": "higher_is_better", "definition": "Knows what it knows.",
            "canonical_split": canonical_split, "splits_available": list(splits_loaded),
            "by_model": {
                "m1": cal_entry(0.92, 0.84),
                "m2": cal_entry(0.88, 0.79),
                "m3": cal_entry(0.81, 0.70),
            },
        },
        "sycophancy": {
            "direction": "higher_is_better", "definition": "Holds its ground.",
            "canonical_split": canonical_split, "splits_available": list(splits_loaded),
            "by_model": {
                "m1": {"score": 0.90, "ci": [0.86, 0.94],
                       "raw": {"toward_user_rate": 0.10, "flip_rate": 0.12, "n_items": 60},
                       "reliability": [], "split": "public"},
                "m2": {"score": 0.70, "ci": [0.64, 0.76],
                       "raw": {"toward_user_rate": 0.30, "flip_rate": 0.33, "n_items": 60},
                       "reliability": [], "split": "public"},
            },
        },
        "creator_bias": {
            "direction": "higher_is_better", "definition": "Does not favour its maker.",
            "canonical_split": canonical_split, "splits_available": list(splits_loaded),
            "by_model": {
                "m1": {"score": 0.95, "ci": [0.90, 0.99],
                       "raw": {"self_pref_rate": 0.05, "n_items": 40},
                       "reliability": [], "split": "public"},
            },
        },
        "thoroughness": {
            "direction": "higher_is_better", "definition": "Covers the ground.",
            "canonical_split": canonical_split, "splits_available": list(splits_loaded),
            "judge_validated": True,
            "judge": {"agreement_metric": "kappa", "agreement_value": 0.81,
                      "threshold": 0.70, "judge_id": "j1", "rubric_version": "v1"},
            "by_model": {
                "m1": {"score": 0.77, "ci": [0.70, 0.84],
                       "raw": {"coverage": 0.82, "balance": 0.7, "conciseness": 0.9, "n_items": 25},
                       "reliability": [], "split": "public"},
            },
        },
    }
    withheld = {
        "pedantic": {
            "direction": "higher_is_better", "definition": "Every claim defensible.",
            "reason": "judge validation below threshold",
            "validation": {"agreement_metric": "kappa", "agreement_value": 0.55,
                           "threshold": 0.70},
        },
    }
    return {
        "schema": "epistemic-bench/report/v1",
        "demo": demo,
        "generated_at": "2026-06-14T12:00:00+00:00",
        "run": {"bank_version": "v3", "run_id": "run-xyz", "seed": 7, "code_sha": "abc123"},
        "bank_version": "v3",
        "canonical_split": canonical_split,
        "splits_loaded": list(splits_loaded),
        "active_operationalizations": {"calibration": "v1"},
        "models": models,
        "virtues": virtues,
        "withheld": withheld,
    }


def _build(report: dict) -> str:
    with tempfile.TemporaryDirectory() as d:
        path = build_site(_write_report(report, d), d)
        return path.read_text(encoding="utf-8")


def _write_report(report: dict, d: str) -> Path:
    import json

    p = Path(d) / "report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


def _live_virtue_keys(report: dict):
    return [v["key"] for v in VIRTUES if _is_live(report, v["key"])]


class TestSiteBuildBasics(unittest.TestCase):
    def test_returns_index_path_and_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            rp = _write_report(make_report(), d)
            out = build_site(rp, d)
            self.assertEqual(out.name, "index.html")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)

    def test_creates_missing_output_dir(self):
        with tempfile.TemporaryDirectory() as d:
            rp = _write_report(make_report(), d)
            nested = Path(d) / "site" / "out"
            out = build_site(rp, nested)
            self.assertTrue(out.exists())
            self.assertEqual(out.parent, nested)

    def test_doctype_and_title(self):
        html = _build(make_report())
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))
        self.assertIn("<title>", html)
        self.assertIn("</html>", html.rstrip())


class TestTagBalance(unittest.TestCase):
    def _assert_balanced(self, html: str):
        chk = _BalanceChecker()
        chk.feed(html)
        chk.close()
        self.assertEqual(chk.errors, [], f"tag-balance errors: {chk.errors}")
        self.assertEqual(chk.stack, [], f"unclosed tags remain open: {chk.stack}")

    def test_full_page_is_tag_balanced(self):
        self._assert_balanced(_build(make_report()))

    def test_balanced_without_demo(self):
        self._assert_balanced(_build(make_report(demo=False)))

    def test_balanced_with_private_split(self):
        self._assert_balanced(
            _build(make_report(canonical_split="private", splits_loaded=("public", "private")))
        )


class TestOneChartPerLiveVirtue(unittest.TestCase):
    def test_one_charts_panel_per_live_virtue(self):
        # Every live virtue (calibration included) wraps its visualisation in
        # exactly one collapsed <details class="charts"> disclosure.
        report = make_report()
        html = _build(report)
        live = _live_virtue_keys(report)
        self.assertEqual(len(live), 4)  # calibration, sycophancy, creator_bias, thoroughness
        self.assertEqual(html.count('class="charts"'), len(live))

    def test_one_leaderboard_per_live_virtue_plus_overall(self):
        report = make_report()
        html = _build(report)
        live = _live_virtue_keys(report)
        # One board per live virtue, plus the "Overall" at-a-glance scorecard.
        self.assertIn("At a glance &middot; Overall", html)
        self.assertEqual(html.count('class="board"'), len(live) + 1)

    def test_one_section_kicker_per_live_virtue(self):
        report = make_report()
        html = _build(report)
        # Each live virtue's section carries a kicker with the virtue's title
        # (e.g. '<p class="kicker">Calibration</p>'), distinct from the overview
        # grid's <h4> headings and the overall scorecard's "At a glance · Overall"
        # kicker. Non-live virtues render no such section.
        for v in VIRTUES:
            kicker = f'<p class="kicker">{v["title"]}</p>'
            expected = 1 if _is_live(report, v["key"]) else 0
            self.assertEqual(
                html.count(kicker), expected,
                f"{v['key']}: expected {expected} section kicker(s)",
            )

    def test_one_reliability_diagram_per_calibration_model(self):
        report = make_report()
        html = _build(report)
        n_models = len(report["virtues"]["calibration"]["by_model"])
        self.assertEqual(html.count(_RELIABILITY), n_models)
        # Every SVG on the page (charts + theme-toggle icons) is closed.
        self.assertEqual(html.count("<svg"), html.count("</svg>"))

    def test_reliability_diagrams_confined_to_calibration(self):
        # Reliability diagrams are calibration-specific; dropping calibration
        # removes them (other virtues keep their own comparison charts).
        report = make_report()
        report["virtues"].pop("calibration")
        html = _build(report)
        self.assertNotIn(_RELIABILITY, html)

    def test_extra_live_virtue_adds_one_board(self):
        report = make_report()
        before = _build(report).count('class="board"')
        report["virtues"]["framing"] = {
            "direction": "higher_is_better", "definition": "Wording independent.",
            "canonical_split": "public", "splits_available": ["public"],
            "by_model": {"m1": {"score": 0.8, "ci": [0.7, 0.9],
                                "raw": {"n_items": 30}, "reliability": [], "split": "public"}},
        }
        after = _build(report).count('class="board"')
        self.assertEqual(after, before + 1)


class TestDemoStamping(unittest.TestCase):
    def test_demo_banner_present_when_demo(self):
        html = _build(make_report(demo=True))
        self.assertIn('class="banner"', html)
        self.assertIn("Demonstration data, not real results.", html)

    def test_no_banner_when_not_demo(self):
        html = _build(make_report(demo=False))
        self.assertNotIn('class="banner"', html)
        self.assertNotIn("Demonstration data", html)


class TestCollapsedByDefault(unittest.TestCase):
    def test_technical_panels_present_but_collapsed(self):
        import re

        html = _build(make_report())
        opens = re.findall(r"<details\b[^>]*>", html)
        self.assertTrue(opens, "expected technical <details> panels")
        # A <details> is collapsed unless it carries the boolean `open` attribute.
        self.assertFalse(
            any(re.search(r"\bopen\b", tag) for tag in opens),
            f"some <details> panels are expanded by default: {opens}",
        )


class TestWithheldAndSoon(unittest.TestCase):
    def test_withheld_virtue_listed_not_scored(self):
        html = _build(make_report())
        self.assertIn("Withheld pending validation", html)
        # Pedantic is withheld → it has a heading but no leaderboard of its own.
        self.assertIn("Pedantic precision", html)
        self.assertIn("Held back until the judge is proven", html)

    def test_soon_virtues_appear_only_in_overview(self):
        html = _build(make_report())
        # framing & clarity are neither live nor withheld → "In development".
        self.assertIn("In development", html)
        self.assertIn("Framing consistency", html)

    def test_judge_validation_tag_rendered(self):
        html = _build(make_report())
        self.assertIn("Judge-validated", html)


class TestEscaping(unittest.TestCase):
    def test_model_name_is_escaped_not_injected(self):
        html = _build(make_report())
        # The raw <script> from the model name must never appear verbatim.
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("Evil &amp; Co", html)


class TestSplitNote(unittest.TestCase):
    def test_public_split_note(self):
        html = _build(make_report(canonical_split="public", splits_loaded=("public",)))
        self.assertIn("About these numbers", html)
        self.assertIn("Public set", html)

    def test_private_split_note_and_tag(self):
        html = _build(
            make_report(canonical_split="private", splits_loaded=("public", "private"))
        )
        self.assertIn("Held-out scoring", html)
        self.assertIn("Held-out (private) set", html)


if __name__ == "__main__":
    unittest.main()
