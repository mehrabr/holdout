"""Tests for report/render.py.

Covers the faithfulness and structural properties specified in the testing strategy:
  - Every rationale appears verbatim in the output.
  - Minority positions labelled 'on record', never 'error' or 'rejected'.
  - No synthesized text (Invariant I faithfulness check).
  - SPLIT renders crux + escalation language; MAJORITY and FRAGILE_AGREEMENT do not.
  - FRAGILE_AGREEMENT renders a concurrence note; MAJORITY and SPLIT do not.
  - Record identifier present for citation.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from holdout.report.render import render
from holdout.types import Outcome, Position, Record, Tier, Vote

# ── helpers ───────────────────────────────────────────────────────────────────


def _pos(name: str, mandate: str, rationale: str, vote: Vote) -> Position:
    return Position(agent_name=name, agent_mandate=mandate, rationale=rationale, vote=vote)


def _stripped(html: str) -> str:
    """Return visible text content: removes style/script blocks then all HTML tags."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"<[^>]+>", " ", text)


_MAJORITY_RECORD = Record(
    id="rpt-majority-1",
    created_at="2024-03-01T12:00:00Z",
    question="Should we adopt the new library?",
    tier=Tier.REVERSIBLE,
    outcome=Outcome.MAJORITY,
    positions=(
        _pos("empirical", "reason from data", "data supports it SENTINEL_E", Vote.YES),
        _pos("principled", "reason from duty", "duty requires it SENTINEL_P", Vote.YES),
        _pos("practitioner", "reason from pattern", "pattern says caution SENTINEL_X", Vote.NO),
    ),
)

_SPLIT_RECORD = Record(
    id="rpt-split-1",
    created_at="2024-03-02T12:00:00Z",
    question="Should we migrate the auth service?",
    tier=Tier.HARD_TO_REVERSE,
    outcome=Outcome.SPLIT,
    crux="Will the migration cause irrecoverable data loss for active users?",
    positions=(
        _pos("empirical", "reason from data", "metrics show risk SENTINEL_E", Vote.NO),
        _pos("principled", "reason from duty", "duty to users first SENTINEL_P", Vote.YES),
        _pos("practitioner", "reason from pattern", "prior migrations failed SENTINEL_X", Vote.NO),
    ),
)

_FRAGILE_RECORD = Record(
    id="rpt-fragile-1",
    created_at="2024-03-03T12:00:00Z",
    question="Should we rewrite in Rust?",
    tier=Tier.HARD_TO_REVERSE,
    outcome=Outcome.FRAGILE_AGREEMENT,
    concurrence=True,
    positions=(
        _pos("empirical", "reason from data", "perf data supports it SENTINEL_E", Vote.YES),
        _pos("principled", "reason from duty", "team competence matters SENTINEL_P", Vote.YES),
        _pos("practitioner", "reason from pattern", "rewrites rarely pay off SENTINEL_X", Vote.YES),
    ),
)


# ── rationale verbatim ────────────────────────────────────────────────────────


def test_majority_all_rationales_appear_verbatim() -> None:
    html = render(_MAJORITY_RECORD)
    for p in _MAJORITY_RECORD.positions:
        assert p.rationale in html, f"rationale for {p.agent_name!r} missing from output"


def test_split_all_rationales_appear_verbatim() -> None:
    html = render(_SPLIT_RECORD)
    for p in _SPLIT_RECORD.positions:
        assert p.rationale in html


def test_fragile_all_rationales_appear_verbatim() -> None:
    html = render(_FRAGILE_RECORD)
    for p in _FRAGILE_RECORD.positions:
        assert p.rationale in html


# ── minority labelling ────────────────────────────────────────────────────────


def test_minority_labelled_on_record_for_majority() -> None:
    """The outvoted 'practitioner' position must be labelled 'on record'."""
    html = render(_MAJORITY_RECORD)
    # The minority agent is 'practitioner' (voted NO against YES majority).
    # Verify the label appears in the output.
    assert "position on record" in html


def test_minority_label_not_error_or_rejected() -> None:
    """Minority must never be labelled 'error' or 'rejected'."""
    html = render(_MAJORITY_RECORD)
    text = _stripped(html)
    assert "error" not in text.lower()
    assert "rejected" not in text.lower()


def test_unanimous_outcomes_have_no_on_record_label() -> None:
    """FRAGILE_AGREEMENT is unanimous — no outvoted position to label."""
    html = render(_FRAGILE_RECORD)
    assert "position on record" not in html


def test_split_has_no_on_record_minority_label() -> None:
    """On SPLIT there is no prevailing side, so no 'on record' minority label."""
    html = render(_SPLIT_RECORD)
    assert "position on record" not in html


# ── no synthesis (faithfulness, Invariant I) ──────────────────────────────────


def test_record_id_appears_for_citation() -> None:
    for rec in (_MAJORITY_RECORD, _SPLIT_RECORD, _FRAGILE_RECORD):
        html = render(rec)
        assert rec.id in html, f"record id {rec.id!r} not found in output"


def test_question_appears_verbatim() -> None:
    for rec in (_MAJORITY_RECORD, _SPLIT_RECORD, _FRAGILE_RECORD):
        html = render(rec)
        assert rec.question in html


def test_agent_mandates_appear_in_output() -> None:
    html = render(_MAJORITY_RECORD)
    for p in _MAJORITY_RECORD.positions:
        assert p.agent_mandate in html


# ── outcome-specific rendering ────────────────────────────────────────────────


def test_split_renders_crux_verbatim() -> None:
    html = render(_SPLIT_RECORD)
    assert _SPLIT_RECORD.crux in html  # type: ignore[operator]


def test_split_renders_escalation_language() -> None:
    """The report must convey that the panel could not reach a verdict."""
    text = _stripped(render(_SPLIT_RECORD))
    assert "split" in text.lower() or "could not reach a verdict" in text.lower()


def test_majority_does_not_render_crux() -> None:
    text = _stripped(render(_MAJORITY_RECORD))
    assert "crux" not in text.lower()


def test_majority_does_not_render_fragile_note() -> None:
    text = _stripped(render(_MAJORITY_RECORD))
    assert "fragile" not in text.lower()


def test_fragile_renders_concurrence_note() -> None:
    text = _stripped(render(_FRAGILE_RECORD))
    assert "fragile" in text.lower()
    assert "incompatible" in text.lower() or "fragile agreement" in text.lower()


def test_fragile_does_not_render_crux() -> None:
    text = _stripped(render(_FRAGILE_RECORD))
    assert "crux" not in text.lower()


def test_split_does_not_render_fragile_note() -> None:
    html = render(_SPLIT_RECORD)
    assert "fragile agreement" not in _stripped(html).lower()


# ── tally ─────────────────────────────────────────────────────────────────────


def test_majority_tally_counts_appear() -> None:
    html = render(_MAJORITY_RECORD)
    # 2 YES, 1 NO
    assert "YES: 2" in html
    assert "NO: 1" in html


def test_split_tally_counts_appear() -> None:
    html = render(_SPLIT_RECORD)
    # 1 YES, 2 NO
    assert "YES: 1" in html
    assert "NO: 2" in html


# ── output is valid HTML and self-contained ───────────────────────────────────


def test_output_is_html_document() -> None:
    html = render(_MAJORITY_RECORD)
    assert html.lstrip().startswith("<!DOCTYPE html")
    assert "</html>" in html


def test_no_external_resources() -> None:
    """Self-contained: no <link>, <script src>, or <img src> pointing outward."""
    html = render(_MAJORITY_RECORD)
    assert 'href="http' not in html
    assert 'src="http' not in html


# ── image rendering ───────────────────────────────────────────────────────────


def test_url_image_appears_in_report() -> None:
    """A URL image must appear as an <img src> in the report."""
    url = "https://example.com/diagram.png"
    html = render(_MAJORITY_RECORD, images=[url])
    assert url in html
    assert "<img" in html


def test_url_image_renders_visual_context_section() -> None:
    html = render(_MAJORITY_RECORD, images=["https://example.com/x.png"])
    assert "Visual Context" in html


def test_local_image_embedded_as_data_uri(tmp_path: Path) -> None:
    """A local file must be embedded as a data URI (self-contained report)."""
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    html = render(_MAJORITY_RECORD, images=[str(img)])
    assert "data:image/png;base64," in html
    assert 'src="http' not in html  # no external reference to the local file


def test_local_image_data_uri_content_matches_file(tmp_path: Path) -> None:
    """The embedded data URI must contain the exact bytes of the original file."""
    raw = b"\x89PNG\r\n\x1a\n" + b"FAKE_PNG_BODY"
    img = tmp_path / "test.png"
    img.write_bytes(raw)
    html = render(_MAJORITY_RECORD, images=[str(img)])
    expected_b64 = base64.b64encode(raw).decode()
    assert expected_b64 in html


def test_no_images_no_visual_context_section() -> None:
    """Without images the report must not contain a Visual Context section."""
    html = render(_MAJORITY_RECORD)
    assert "Visual Context" not in html
    assert "<img" not in html


def test_multiple_images_all_appear(tmp_path: Path) -> None:
    """Every image in the list must appear in the report."""
    img1 = tmp_path / "a.png"
    img1.write_bytes(b"AAAAAA")
    url = "https://example.com/b.png"
    html = render(_MAJORITY_RECORD, images=[str(img1), url])
    assert url in html
    assert base64.b64encode(b"AAAAAA").decode() in html
